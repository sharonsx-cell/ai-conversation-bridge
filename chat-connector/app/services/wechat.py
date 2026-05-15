import hashlib
import logging
import threading
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class WeChatClient:
    """WeChat Official Account API: access token + customer-service text messages."""

    TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
    CUSTOM_SEND_URL = "https://api.weixin.qq.com/cgi-bin/message/custom/send"

    def __init__(
        self,
        app_id: Optional[str],
        app_secret: Optional[str],
        token: Optional[str],
    ):
        self._app_id = app_id
        self._app_secret = app_secret
        self._token = token  # webhook signature token (from MP admin console)
        self._access_token: Optional[str] = None
        self._access_token_expire_at_ms: float = 0.0
        self._lock = threading.Lock()

    def validate_config(self) -> bool:
        return bool(self._app_id and self._app_secret and self._token)

    @staticmethod
    def verify_signature(
        signature: str,
        timestamp: str,
        nonce: str,
        token: str,
    ) -> bool:
        parts = sorted([token, timestamp, nonce])
        # WeChat MP server config requires SHA1 for this signature (not configurable).
        digest = hashlib.sha1("".join(parts).encode("utf-8")).hexdigest()  # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1
        return digest == signature

    def check_request_signature(
        self,
        signature: Optional[str],
        timestamp: Optional[str],
        nonce: Optional[str],
    ) -> bool:
        if not signature or not timestamp or not nonce or not self._token:
            return False
        return self.verify_signature(signature, timestamp, nonce, self._token)

    def get_access_token(self) -> str:
        now = time.time() * 1000
        with self._lock:
            if self._access_token and now < self._access_token_expire_at_ms - 60_000:
                return self._access_token

        if not self._app_id or not self._app_secret:
            raise RuntimeError("WECHAT_APP_ID or WECHAT_APP_SECRET missing")

        params = {
            "grant_type": "client_credential",
            "appid": self._app_id,
            "secret": self._app_secret,
        }
        with httpx.Client(timeout=10.0) as client:
            r = client.get(self.TOKEN_URL, params=params)
            r.raise_for_status()
            data = r.json()

        if data.get("errcode"):
            raise RuntimeError(f"WeChat token API error: {data.get('errmsg')}")

        access_token = data["access_token"]
        expire_sec = int(data.get("expires_in", 7200))
        with self._lock:
            self._access_token = access_token
            self._access_token_expire_at_ms = time.time() * 1000 + expire_sec * 1000
        logger.info("WeChat access token refreshed")
        return access_token

    def send_text_to_user(self, openid: str, text: str, timeout: float = 10.0) -> dict[str, Any]:
        access_token = self.get_access_token()
        url = f"{self.CUSTOM_SEND_URL}?access_token={access_token}"
        body = {
            "touser": openid,
            "msgtype": "text",
            "text": {"content": text},
        }
        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, json=body)
            r.raise_for_status()
            data = r.json()

        if data.get("errcode", 0) != 0:
            logger.error("WeChat custom send error: %s", data)
        return data
