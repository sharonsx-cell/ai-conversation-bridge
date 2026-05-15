import logging
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


def _find_first_string(obj: Any) -> Optional[str]:
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            found = _find_first_string(v)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_first_string(item)
            if found:
                return found
    return None


def _parse_flowise_body(data: Any) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data.strip()

    if isinstance(data, dict):
        if data.get("text"):
            return str(data["text"]).strip()
        if data.get("response"):
            return str(data["response"]).strip()
        inner = data.get("data")
        if isinstance(inner, dict):
            t = inner.get("text") or inner.get("response")
            if t:
                return str(t).strip()
            return _find_first_string(inner) or ""
        found = _find_first_string(data)
        if found:
            return found.strip()
        return ""

    return str(data).strip()


class FlowiseClient:
    """Primary chat provider via Flowise prediction API."""

    def __init__(self, api_url: Optional[str], api_key: Optional[str] = None, timeout: int = 120):
        self.api_url = api_url
        self.api_key = api_key
        self.timeout = timeout

    def get_completion(
        self,
        user_message: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        if not self.api_url:
            logger.error("FLOWISE_API_URL not set.")
            return "I am currently unable to think (Configuration Error)."

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, Any] = {"question": user_message}
        sid = session_id or user_id
        if sid:
            payload["overrideConfig"] = {"sessionId": sid}

        t0 = time.time()
        try:
            with httpx.Client() as client:
                response = client.post(
                    self.api_url, headers=headers, json=payload, timeout=self.timeout
                )
            elapsed = time.time() - t0
            response.raise_for_status()
            data = response.json()
            text = _parse_flowise_body(data)
            logger.info("Flowise responded in %.1fs", elapsed)
            return text

        except httpx.TimeoutException as e:
            elapsed = time.time() - t0
            logger.error("Flowise timeout after %.1fs: %s", elapsed, e)
            return (
                "Sorry, the AI service is taking longer than expected. "
                "Please try again in a moment."
            )
        except httpx.HTTPStatusError as e:
            elapsed = time.time() - t0
            status = e.response.status_code
            logger.error("Flowise HTTP %s after %.1fs: %s", status, elapsed, e)
            if status == 429:
                return (
                    "The AI service is temporarily rate-limited. "
                    "Please wait a moment and try again."
                )
            return "Sorry, the AI service returned an error. Please try again later."
        except Exception as e:
            elapsed = time.time() - t0
            logger.error(
                "Flowise call failed after %.1fs (%s): %s",
                elapsed,
                type(e).__name__,
                e,
            )
            return "Sorry, I encountered an error while processing your request."
