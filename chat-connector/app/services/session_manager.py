import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ChatSession:
    session_id: str
    chat_id: str
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    message_count: int = 0
    last_message: Optional[str] = None
    pending_feedback: bool = False
    is_new_session: bool = True


class SessionManager:
    """Per-chat_id sessions with timeout and periodic cleanup (ported from app.js)."""

    def __init__(self, session_timeout_ms: int):
        self._session_timeout_ms = session_timeout_ms
        self._sessions: Dict[str, ChatSession] = {}
        self._lock = threading.Lock()
        self._cleanup_started = False

    def start_cleanup_background(self, interval_ms: int) -> None:
        if self._cleanup_started:
            return
        self._cleanup_started = True

        def loop() -> None:
            while True:
                time.sleep(max(1.0, interval_ms / 1000.0))
                try:
                    self.cleanup_expired_sessions()
                except Exception as e:
                    logger.exception("Session cleanup failed: %s", e)

        threading.Thread(target=loop, daemon=True).start()

    def get_session(self, chat_id: str, force_new: bool = False) -> ChatSession:
        now = time.time() * 1000
        with self._lock:
            if force_new or chat_id not in self._sessions:
                return self._create_new_session_locked(chat_id)

            session = self._sessions[chat_id]
            if now - session.last_activity > self._session_timeout_ms:
                logger.info(
                    "Session %s timed out (~%s min), creating new session",
                    chat_id,
                    round((now - session.last_activity) / 60000),
                )
                return self._create_new_session_locked(chat_id)

            session.last_activity = now
            return session

    def _create_new_session_locked(self, chat_id: str) -> ChatSession:
        session_id = f"{chat_id}_{int(time.time() * 1000)}"
        session = ChatSession(session_id=session_id, chat_id=chat_id)
        self._sessions[chat_id] = session
        logger.info("Created session_id=%s for chat_id=%s", session_id, chat_id)
        return session

    def update_session_activity(self, chat_id: str) -> None:
        now = time.time() * 1000
        with self._lock:
            s = self._sessions.get(chat_id)
            if s:
                s.last_activity = now
                s.is_new_session = False

    def reset_session(self, chat_id: str) -> ChatSession:
        with self._lock:
            return self._create_new_session_locked(chat_id)

    def set_pending_feedback(self, chat_id: str, value: bool) -> None:
        with self._lock:
            s = self._sessions.get(chat_id)
            if s:
                s.pending_feedback = value

    def record_user_message(self, chat_id: str, user_message: str) -> None:
        now = time.time() * 1000
        with self._lock:
            s = self._sessions.get(chat_id)
            if not s:
                return
            s.message_count += 1
            s.last_message = user_message
            s.last_activity = now

    def cleanup_expired_sessions(self) -> None:
        now = time.time() * 1000
        expiration_ms = 24 * 60 * 60 * 1000
        with self._lock:
            to_delete = [
                cid
                for cid, s in self._sessions.items()
                if now - s.last_activity > expiration_ms
            ]
            for cid in to_delete:
                s = self._sessions.pop(cid, None)
                if s:
                    logger.info(
                        "Cleaned expired session chat_id=%s session_id=%s",
                        cid,
                        s.session_id,
                    )

    def list_sessions_summary(self) -> list[dict[str, Any]]:
        now = time.time() * 1000
        with self._lock:
            out = []
            for chat_id, s in self._sessions.items():
                inactive_min = round((now - s.last_activity) / 60000)
                out.append(
                    {
                        "chat_id_prefix": chat_id[:20] + ("..." if len(chat_id) > 20 else ""),
                        "session_id_prefix": s.session_id[:30] + "...",
                        "message_count": s.message_count,
                        "inactive_minutes": inactive_min,
                        "is_expired": inactive_min > 10,
                    }
                )
            return out

    def active_count(self) -> int:
        with self._lock:
            return len(self._sessions)
