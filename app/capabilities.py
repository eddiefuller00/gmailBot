from __future__ import annotations

from app import db
from app.ai_runtime import openai_available
from app.config import settings
from app.schemas import CapabilitiesResponse, CapabilityStatus
from app.security import token_encryption_enabled


def _state_value(key: str) -> tuple[str | None, object | None]:
    record = db.get_runtime_state(key)
    if not record:
        return None, None
    return record["value"], record["updated_at"]


def get_capabilities() -> CapabilitiesResponse:
    openai_configured = bool(settings.openai_api_key)
    gmail_oauth_configured = bool(
        settings.google_client_id
        and settings.google_client_secret
        and settings.google_redirect_uri
    )
    encryption_available = token_encryption_enabled()

    last_sync_value, _ = _state_value("last_successful_sync_at")
    last_ai_error, last_ai_error_at = _state_value("last_ai_error")

    openai_status = CapabilityStatus(
        configured=openai_configured,
        available=openai_available(),
        message=(
            "OpenAI is ready for ingestion, ranking, alerts, and Ask Inbox."
            if openai_available()
            else "Set `OPENAI_API_KEY` to enable AI ranking, alerts, and Ask Inbox."
        ),
    )
    gmail_status = CapabilityStatus(
        configured=gmail_oauth_configured,
        available=gmail_oauth_configured,
        message=(
            "Google OAuth is configured."
            if gmail_oauth_configured
            else "Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI`."
        ),
    )
    encryption_status = CapabilityStatus(
        configured=bool(settings.token_encryption_key),
        available=encryption_available,
        message=(
            "Encrypted token storage is enabled."
            if encryption_available
            else "Set `TOKEN_ENCRYPTION_KEY`; plaintext Gmail token storage is disabled."
        ),
    )

    return CapabilitiesResponse(
        openai=openai_status,
        gmail_oauth=gmail_status,
        token_encryption=encryption_status,
        can_rank_inbox=openai_status.available,
        can_sync_gmail=(
            openai_status.available
            and gmail_status.available
            and encryption_status.available
        ),
        last_successful_sync_at=last_sync_value,
        last_ai_error=last_ai_error,
        last_ai_error_at=last_ai_error_at,
    )
