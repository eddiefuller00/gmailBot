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
    openai_runtime_available = openai_available()
    gmail_oauth_configured = bool(
        settings.google_client_id
        and settings.google_client_secret
        and settings.google_redirect_uri
    )
    encryption_available = token_encryption_enabled()

    last_sync_value, _ = _state_value("last_successful_sync_at")
    last_ai_error, last_ai_error_at = _state_value("last_ai_error")
    last_ai_success_at, _ = _state_value("last_ai_success_at")

    if openai_runtime_available and last_ai_error:
        openai_message = "OpenAI is configured, but the last runtime call failed. Check runtime logs and retry."
    elif openai_runtime_available and last_ai_success_at:
        openai_message = "OpenAI is ready for ingestion, ranking, alerts, and Ask Inbox."
    elif openai_runtime_available:
        openai_message = (
            "OpenAI is configured, but the runtime has not completed a successful model call yet."
        )
    else:
        openai_message = "Set `OPENAI_API_KEY` to enable AI ranking, alerts, and Ask Inbox."

    openai_status = CapabilityStatus(
        configured=openai_configured,
        available=openai_runtime_available,
        message=openai_message,
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
