import logging
import threading

from flask import (
    Blueprint,
    Response,
    copy_current_request_context,
    current_app,
    jsonify,
    request,
)

from app.config import Config
from app.response_validator import ResponseValidator
from app.services.flowise import FlowiseClient
from app.services.lineworks import LineWorksClient
from app.services.message_pipeline import process_text_message
from app.services.openrouter import OpenRouterClient
from app.services.session_manager import SessionManager
from app.services.wechat import WeChatClient
from app.services.xml_utils import parse_wechat_xml

bp = Blueprint("main", __name__)
logger = logging.getLogger(__name__)

lw_client = LineWorksClient(Config)

session_manager = SessionManager(Config.SESSION_TIMEOUT_MS)
session_manager.start_cleanup_background(Config.SESSION_CLEANUP_INTERVAL_MS)

wechat_client = WeChatClient(
    Config.WECHAT_APP_ID,
    Config.WECHAT_APP_SECRET,
    Config.WECHAT_TOKEN,
)

if Config.CHAT_PROVIDER == "openrouter":
    logger.info("Using OpenRouter as chat provider (demo/experiment)")
    ai_client = OpenRouterClient(
        Config.OPENROUTER_API_KEY,
        Config.OPENROUTER_MODEL,
        Config.OPENROUTER_API_URL,
        Config.OPENROUTER_SYSTEM_PROMPT,
        Config.OPENROUTER_REASONING_EFFORT,
    )
else:
    logger.info("Using Flowise as chat provider")
    ai_client = FlowiseClient(
        Config.FLOWISE_API_URL,
        Config.FLOWISE_API_KEY,
        Config.FLOWISE_TIMEOUT,
    )


def _status_html() -> str:
    base = (Config.PUBLIC_BASE_URL or "").rstrip("/")
    webhook_hint = f"{base}/webhook" if base else "GET/POST /webhook"
    rows = session_manager.list_sessions_summary()
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>AI Conversation Bridge — chat-connector</title>",
        "<style>body{font-family:sans-serif;padding:20px}"
        ".session{border:1px solid #ddd;padding:10px;margin:10px 0;border-radius:5px}"
        ".expired{background:#ffe6e6}.active{background:#e6ffe6}.muted{color:#666;font-size:.9em}</style>",
        "</head><body>",
        "<h1>chat-connector</h1>",
        "<p><strong>Status:</strong> <span style='color:green'>online</span></p>",
        f"<p><strong>Provider:</strong> {Config.CHAT_PROVIDER}</p>",
        f"<p><strong>WeChat sessions:</strong> {session_manager.active_count()}</p>",
        f"<p><strong>WeChat webhook:</strong> <code>{webhook_hint}</code></p>",
        "<hr><h3>WeChat sessions</h3>",
    ]
    if not rows:
        parts.append("<p>No active sessions.</p>")
    else:
        for s in rows:
            cls = "expired" if s["is_expired"] else "active"
            parts.append(
                f"<div class='session {cls}'><strong>session</strong> {s['session_id_prefix']}<br>"
                f"<strong>messages</strong> {s['message_count']}<br>"
                f"<strong>idle</strong> {s['inactive_minutes']} min<br>"
                f"<span class='muted'>user {s['chat_id_prefix']}</span></div>"
            )
    parts.append("</body></html>")
    return "".join(parts)


@bp.route("/")
def health():
    """Health check endpoint."""
    if Config.ENABLE_STATUS_PAGE:
        return Response(_status_html(), mimetype="text/html; charset=utf-8")
    return jsonify({
        "status": "ok",
        "provider": Config.CHAT_PROVIDER,
        "wechat_sessions": session_manager.active_count(),
    }), 200


@bp.route("/callback", methods=["POST"])
def callback():
    """Handle LINE WORKS message callbacks."""
    try:
        raw_body = request.get_data()
        signature = request.headers.get("X-WORKS-Signature", "")

        if not lw_client.verify_signature(raw_body, signature):
            current_app.logger.warning("Webhook signature verification failed")
            return "Unauthorized", 401

        data = request.get_json(silent=True)
        if data is None:
            current_app.logger.warning("Invalid or empty JSON body")
            return "Bad Request", 400

        current_app.logger.info(
            "Received callback from user: %s",
            data.get("source", {}).get("userId", "unknown"),
        )

        if not data or data.get("type") != "message":
            return "OK", 200

        source = data.get("source")
        user_id = source.get("userId") if source else None

        content_payload = data.get("content", {})
        message_type = content_payload.get("type")
        user_text = content_payload.get("text")

        if not user_id:
            current_app.logger.warning("No userId found in source")
            return "OK", 200

        if message_type != "text" or not user_text:
            current_app.logger.info("Received non-text message or empty text.")
            return "OK", 200

        user_text = user_text.strip()
        if len(user_text) > Config.MAX_MESSAGE_LENGTH:
            current_app.logger.warning(
                "Message from %s exceeds max length (%s > %s)",
                user_id,
                len(user_text),
                Config.MAX_MESSAGE_LENGTH,
            )
            lw_client.send_message(
                user_id,
                {
                    "content": {
                        "type": "text",
                        "text": (
                            f"Your message is too long. Please keep it under "
                            f"{Config.MAX_MESSAGE_LENGTH} characters."
                        ),
                    }
                },
            )
            return "OK", 200

        if not lw_client.validate_config():
            current_app.logger.error("Missing one or more LINE WORKS environment variables.")
            return "Internal Server Error", 500

        ai_response_text = ai_client.get_completion(user_text, user_id=user_id)
        ai_response_text = ResponseValidator.validate(
            str(ai_response_text) if ai_response_text else "",
            user_message=user_text,
        )

        reply_content = {
            "content": {
                "type": "text",
                "text": ai_response_text,
            }
        }

        lw_client.send_message(user_id, reply_content)
        current_app.logger.info("Sent reply to user %s", user_id)

        return "OK", 200

    except Exception as e:
        current_app.logger.error("Error processing callback: %s", e)
        return "Internal Server Error", 500


def _wechat_webhook_handler():
    """WeChat Official Account server URL validation and message intake."""
    if request.method == "GET":
        echostr = request.args.get("echostr", "")
        return Response(echostr, mimetype="text/plain")

    signature = request.args.get("signature", "")
    timestamp = request.args.get("timestamp", "")
    nonce = request.args.get("nonce", "")

    if not wechat_client.check_request_signature(signature, timestamp, nonce):
        logger.error("WeChat webhook signature verification failed")
        return "Forbidden", 403

    xml_body = request.get_data(as_text=True) or ""
    if not xml_body.strip():
        return "success", 200

    try:
        message = parse_wechat_xml(xml_body)
    except Exception as e:
        logger.error("Failed to parse WeChat XML: %s", e)
        return "success", 200

    logger.info("WeChat webhook MsgType=%s", message.get("MsgType"))

    @copy_current_request_context
    def worker():
        try:
            process_text_message(
                message=message,
                wechat=wechat_client,
                session_manager=session_manager,
                ai_client=ai_client,
                chat_provider=Config.CHAT_PROVIDER,
            )
        except Exception as e:
            current_app.logger.error("WeChat background worker failed: %s", e)

    threading.Thread(target=worker, daemon=True).start()
    return "success", 200


@bp.route("/webhook", methods=["GET", "POST"])
@bp.route("/wechat", methods=["GET", "POST"])
def wechat_webhook():
    return _wechat_webhook_handler()
