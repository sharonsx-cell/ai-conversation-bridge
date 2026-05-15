from dotenv import load_dotenv

load_dotenv()

import os


class Config:
    # LINE WORKS API
    LW_CLIENT_ID = os.environ.get("LW_API_20_CLIENT_ID")
    LW_CLIENT_SECRET = os.environ.get("LW_API_20_CLIENT_SECRET")
    LW_SERVICE_ACCOUNT_ID = os.environ.get("LW_API_20_SERVICE_ACCOUNT_ID")
    LW_PRIVATE_KEY = os.environ.get("LW_API_20_PRIVATEKEY")
    LW_BOT_ID = os.environ.get("LW_API_20_BOT_ID")
    LW_BOT_SECRET = os.environ.get("LW_API_20_BOT_SECRET")

    BASE_API_URL = "https://www.worksapis.com/v1.0"
    BASE_AUTH_URL = "https://auth.worksmobile.com/oauth2/v2.0"

    # WeChat Official Account (微信公众平台)
    WECHAT_TOKEN = os.environ.get("WECHAT_TOKEN")
    WECHAT_APP_ID = os.environ.get("WECHAT_APP_ID")
    WECHAT_APP_SECRET = os.environ.get("WECHAT_APP_SECRET")

    # Chat Provider: "flowise" (recommended) or "openrouter" (demo/experiment)
    CHAT_PROVIDER = os.environ.get("CHAT_PROVIDER", "flowise").lower()

    # OpenRouter API (demo/experiment)
    OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
    OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "z-ai/glm-4.5-air:free")
    OPENROUTER_API_URL = os.environ.get(
        "OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions"
    )
    OPENROUTER_SYSTEM_PROMPT = os.environ.get(
        "OPENROUTER_SYSTEM_PROMPT", "You are a helpful assistant."
    )
    OPENROUTER_REASONING_EFFORT = os.environ.get("OPENROUTER_REASONING_EFFORT")

    # Flowise API (primary)
    FLOWISE_API_URL = os.environ.get("FLOWISE_API_URL")
    FLOWISE_API_KEY = os.environ.get("FLOWISE_API_KEY")
    FLOWISE_TIMEOUT = int(os.environ.get("FLOWISE_TIMEOUT", 120))

    # Session behaviour (WeChat multi-turn; optional for LINE WORKS)
    SESSION_TIMEOUT_MS = int(os.environ.get("SESSION_TIMEOUT_MS", str(10 * 60 * 1000)))
    SESSION_CLEANUP_INTERVAL_MS = int(
        os.environ.get("SESSION_CLEANUP_INTERVAL_MS", str(30 * 60 * 1000))
    )

    # App
    PORT = int(os.environ.get("PORT", 8080))
    DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
    ENABLE_STATUS_PAGE = os.environ.get("ENABLE_STATUS_PAGE", "false").lower() == "true"
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")

    # Security
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 1 * 1024 * 1024))
    MAX_MESSAGE_LENGTH = int(os.environ.get("MAX_MESSAGE_LENGTH", 4000))
