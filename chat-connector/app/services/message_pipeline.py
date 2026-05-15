import logging
import re
import time
from typing import Any, Protocol

from app.config import Config
from app.response_validator import ResponseValidator
from app.services.session_manager import SessionManager
from app.services.wechat import WeChatClient

logger = logging.getLogger(__name__)


class AIClient(Protocol):
    def get_completion(self, user_message: str, **kwargs: Any) -> str: ...


def detect_language(text: str) -> str:
    return "zh" if re.search(r"[\u4e00-\u9fff]", text) else "en"


def process_text_message(
    *,
    message: dict[str, Any],
    wechat: WeChatClient,
    session_manager: SessionManager,
    ai_client: AIClient,
    chat_provider: str,
) -> None:
    msg_type = (message.get("MsgType") or "").lower()
    if msg_type != "text":
        logger.info("Ignoring non-text message (%s)", msg_type)
        return

    openid = message.get("FromUserName")
    if not openid:
        logger.error("Missing FromUserName on message")
        return

    user_message = (message.get("Content") or "").strip()
    if not user_message:
        logger.warning("Empty user message; skipping")
        return

    user_language = detect_language(user_message)

    if len(user_message) > Config.MAX_MESSAGE_LENGTH:
        msg = (
            f"消息过长，请控制在 {Config.MAX_MESSAGE_LENGTH} 字以内。"
            if user_language == "zh"
            else f"Your message is too long. Please keep it under {Config.MAX_MESSAGE_LENGTH} characters."
        )
        try:
            wechat.send_text_to_user(openid, msg)
        except Exception as e:
            logger.error("Failed to send length limit message: %s", e)
        return

    logger.info('User %s: "%s"', openid, user_message)

    if not wechat.validate_config():
        logger.error("WeChat configuration incomplete")
        return

    if user_message.lower() in ("/reset", "reset"):
        new_session = session_manager.reset_session(openid)
        msg = (
            f"会话已重置，新会话ID: {new_session.session_id}"
            if user_language == "zh"
            else f"Session reset. New session ID: {new_session.session_id}"
        )
        try:
            wechat.send_text_to_user(openid, msg)
        except Exception as e:
            logger.error("Failed to send reset message: %s", e)
        return

    session = session_manager.get_session(openid)
    session_manager.record_user_message(openid, user_message)

    if session.is_new_session:
        logger.info("Using new session_id=%s", session.session_id)
    else:
        logger.info(
            "Using session_id=%s (last activity ~%ss ago)",
            session.session_id,
            round((time.time() * 1000 - session.last_activity) / 1000),
        )

    processing = (
        "正在查询，请稍候..."
        if user_language == "zh"
        else "Processing your query, please wait..."
    )
    try:
        wechat.send_text_to_user(openid, processing)
    except Exception as e:
        logger.warning("Could not send processing notice: %s", e)

    try:
        if chat_provider == "openrouter":
            ai_raw = ai_client.get_completion(user_message, user_id=openid)
        else:
            ai_raw = ai_client.get_completion(user_message, session_id=session.session_id)

        ai_reply = ResponseValidator.validate(str(ai_raw or ""), user_message=user_message)

        if (
            "Please type 'Send Feedback' to confirm" in ai_reply
            or "请确认发送反馈" in ai_reply
        ):
            session_manager.set_pending_feedback(openid, True)

        send_result = wechat.send_text_to_user(openid, ai_reply)
        if send_result.get("errcode", 0) == 0:
            session_manager.update_session_activity(openid)
        else:
            logger.error("WeChat send returned error payload: %s", send_result)

    except Exception as e:
        logger.exception("Pipeline error: %s", e)
        err = (
            "抱歉，处理您的请求时出现错误。请稍后重试或联系管理员。"
            if user_language == "zh"
            else "Sorry, an error occurred while processing your request. "
            "Please try again later or contact support."
        )
        try:
            wechat.send_text_to_user(openid, err)
        except Exception as send_err:
            logger.error("Failed to send error message: %s", send_err)
