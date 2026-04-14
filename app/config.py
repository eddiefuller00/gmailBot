from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


def _frontend_origins() -> tuple[str, ...]:
    raw = os.getenv(
        "FRONTEND_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
    )
    return tuple(origin.strip() for origin in raw.split(",") if origin.strip())


def _google_scopes() -> tuple[str, ...]:
    raw = os.getenv(
        "GOOGLE_SCOPES",
        (
            "https://www.googleapis.com/auth/gmail.readonly "
            "https://www.googleapis.com/auth/userinfo.email "
            "https://www.googleapis.com/auth/userinfo.profile"
        ),
    )
    normalized = raw.replace(",", " ")
    return tuple(scope.strip() for scope in normalized.split() if scope.strip())


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def _as_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value.strip())
    except ValueError:
        return default


def _as_optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        return None


def _openai_stop_sequences() -> tuple[str, ...]:
    raw = os.getenv("OPENAI_CHAT_STOP_SEQUENCES", "")
    if not raw.strip():
        return ()
    normalized = raw.replace(",", "|")
    return tuple(item.strip() for item in normalized.split("|") if item.strip())


@dataclass(frozen=True)
class Settings:
    app_name: str = "Inbox Intelligence API"
    database_path: str = os.getenv("DATABASE_PATH", "data/inbox_intelligence.db")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_chat_model: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-5.4-mini")
    openai_chat_temperature: float = _as_float(os.getenv("OPENAI_CHAT_TEMPERATURE"), 0.0)
    openai_chat_top_p: float = _as_float(os.getenv("OPENAI_CHAT_TOP_P"), 1.0)
    openai_chat_max_tokens: int = _as_int(os.getenv("OPENAI_CHAT_MAX_TOKENS"), 500)
    openai_chat_frequency_penalty: float = _as_float(
        os.getenv("OPENAI_CHAT_FREQUENCY_PENALTY"), 0.0
    )
    openai_chat_presence_penalty: float = _as_float(
        os.getenv("OPENAI_CHAT_PRESENCE_PENALTY"), 0.0
    )
    openai_chat_seed: int | None = _as_optional_int(os.getenv("OPENAI_CHAT_SEED"))
    openai_chat_stop_sequences: tuple[str, ...] = _openai_stop_sequences()
    openai_embedding_model: str = os.getenv(
        "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
    )
    top_important_default: int = int(os.getenv("TOP_IMPORTANT_DEFAULT", "5"))
    frontend_origins: tuple[str, ...] = _frontend_origins()
    frontend_app_url: str = os.getenv("FRONTEND_APP_URL", frontend_origins[0])

    google_client_id: str | None = os.getenv("GOOGLE_CLIENT_ID")
    google_client_secret: str | None = os.getenv("GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str | None = os.getenv("GOOGLE_REDIRECT_URI")
    google_auth_url: str = os.getenv(
        "GOOGLE_AUTH_URL", "https://accounts.google.com/o/oauth2/v2/auth"
    )
    google_token_url: str = os.getenv(
        "GOOGLE_TOKEN_URL", "https://oauth2.googleapis.com/token"
    )
    google_scopes: tuple[str, ...] = _google_scopes()
    oauth_state_ttl_seconds: int = int(os.getenv("OAUTH_STATE_TTL_SECONDS", "600"))
    token_encryption_key: str | None = os.getenv("TOKEN_ENCRYPTION_KEY")
    allow_insecure_token_storage: bool = _as_bool(
        os.getenv("ALLOW_INSECURE_TOKEN_STORAGE"), True
    )


settings = Settings()
