from __future__ import annotations

import base64
import html
import re
import secrets
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode

import httpx

from app import db
from app.config import settings
from app.schemas import (
    GmailMessageDetail,
    GmailMessageListResponse,
    GmailMessageSummary,
    GoogleConnectionStatus,
)
from app.security import (
    deserialize_token_payload,
    serialize_token_payload,
    token_encryption_enabled,
)


class GoogleOAuthConfigError(RuntimeError):
    pass


class GoogleOAuthFlowError(RuntimeError):
    pass


class GmailNotConnectedError(RuntimeError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_google_oauth_config() -> None:
    missing = []
    if not settings.google_client_id:
        missing.append("GOOGLE_CLIENT_ID")
    if not settings.google_client_secret:
        missing.append("GOOGLE_CLIENT_SECRET")
    if not settings.google_redirect_uri:
        missing.append("GOOGLE_REDIRECT_URI")

    if missing:
        raise GoogleOAuthConfigError(
            f"Missing Google OAuth configuration: {', '.join(missing)}"
        )


def _token_response_to_payload(data: dict[str, Any]) -> dict[str, Any]:
    expires_in = int(data.get("expires_in", 3600))
    return {
        "access_token": data.get("access_token"),
        "refresh_token": data.get("refresh_token"),
        "token_type": data.get("token_type", "Bearer"),
        "scope": data.get("scope", ""),
        "expires_at": (_utc_now() + timedelta(seconds=expires_in)).isoformat(),
    }


def _store_tokens(
    *,
    token_payload: dict[str, Any],
    email: str | None,
    scopes: list[str],
) -> None:
    serialized, is_encrypted = serialize_token_payload(token_payload)
    db.save_google_oauth_token(
        token_data=serialized,
        is_encrypted=is_encrypted,
        email=email,
        scopes=scopes,
    )


def _load_token_record() -> tuple[dict[str, Any], dict[str, Any]]:
    token_record = db.get_google_oauth_token()
    if not token_record:
        raise GmailNotConnectedError("Google account is not connected.")
    payload = deserialize_token_payload(
        token_data=token_record["token_data"],
        is_encrypted=token_record["is_encrypted"],
    )
    return token_record, payload


def _http_post_form(url: str, form_data: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            url,
            data=form_data,
            headers={"Accept": "application/json"},
        )
    if response.status_code >= 400:
        raise GoogleOAuthFlowError(
            f"Google token request failed ({response.status_code}): {response.text}"
        )
    return response.json()


def _gmail_get_json(path: str, *, params: Any | None = None) -> dict[str, Any]:
    access_token = get_valid_access_token()
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"https://gmail.googleapis.com{path}",
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if response.status_code == 401:
        # Access token may have expired server-side; refresh and retry once.
        access_token = get_valid_access_token(force_refresh=True)
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"https://gmail.googleapis.com{path}",
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Gmail API request failed ({response.status_code}): {response.text}"
        )
    return response.json()


def _get_gmail_profile(access_token: str) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/profile",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if response.status_code >= 400:
        raise GoogleOAuthFlowError(
            f"Failed to fetch Gmail profile ({response.status_code}): {response.text}"
        )
    return response.json()


def get_google_connection_status() -> GoogleConnectionStatus:
    configured = bool(
        settings.google_client_id
        and settings.google_client_secret
        and settings.google_redirect_uri
    )
    token_record = db.get_google_oauth_token()
    if not token_record:
        return GoogleConnectionStatus(
            configured=configured,
            connected=False,
            token_encrypted=token_encryption_enabled(),
            insecure_storage=False,
        )

    return GoogleConnectionStatus(
        configured=configured,
        connected=True,
        email=token_record["email"],
        scopes=token_record["scopes"],
        connected_at=token_record["connected_at"],
        token_encrypted=token_record["is_encrypted"],
        insecure_storage=not token_record["is_encrypted"],
    )


def build_google_auth_url() -> str:
    _require_google_oauth_config()
    state = secrets.token_urlsafe(32)
    expires_at = _utc_now() + timedelta(seconds=settings.oauth_state_ttl_seconds)
    db.create_google_oauth_state(state=state, expires_at=expires_at)

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(settings.google_scopes),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    return f"{settings.google_auth_url}?{urlencode(params)}"


def _exchange_code_for_tokens(code: str) -> dict[str, Any]:
    _require_google_oauth_config()
    form_data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri,
    }
    return _http_post_form(settings.google_token_url, form_data)


def _refresh_access_token(refresh_token: str) -> dict[str, Any]:
    _require_google_oauth_config()
    form_data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
    }
    return _http_post_form(settings.google_token_url, form_data)


def handle_google_callback(*, code: str, state: str) -> str | None:
    if not db.consume_google_oauth_state(state):
        raise GoogleOAuthFlowError("Invalid or expired OAuth state.")

    token_response = _exchange_code_for_tokens(code)
    token_payload = _token_response_to_payload(token_response)
    current_record = db.get_google_oauth_token()
    if not token_payload.get("refresh_token") and current_record:
        current = deserialize_token_payload(
            current_record["token_data"], current_record["is_encrypted"]
        )
        token_payload["refresh_token"] = current.get("refresh_token")

    access_token = token_payload.get("access_token")
    if not access_token:
        raise GoogleOAuthFlowError("Google OAuth callback did not return access token.")

    profile = _get_gmail_profile(access_token)
    email = profile.get("emailAddress")
    scopes = token_response.get("scope", "")
    scope_list = [s for s in str(scopes).split(" ") if s] or list(settings.google_scopes)
    _store_tokens(token_payload=token_payload, email=email, scopes=scope_list)
    return email


def disconnect_google_account() -> None:
    db.clear_google_oauth_token()


def get_valid_access_token(*, force_refresh: bool = False) -> str:
    token_record, payload = _load_token_record()
    if not payload.get("refresh_token") and (
        force_refresh or not payload.get("access_token")
    ):
        raise GmailNotConnectedError(
            "Missing refresh token. Reconnect Google account with prompt=consent."
        )

    expires_at_raw = payload.get("expires_at")
    expires_at = None
    if isinstance(expires_at_raw, str):
        try:
            expires_at = datetime.fromisoformat(expires_at_raw)
        except ValueError:
            expires_at = None
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if not force_refresh and payload.get("access_token") and expires_at:
        if expires_at > (_utc_now() + timedelta(seconds=60)):
            return str(payload["access_token"])

    refreshed = _refresh_access_token(str(payload["refresh_token"]))
    new_payload = _token_response_to_payload(refreshed)
    if not new_payload.get("refresh_token"):
        new_payload["refresh_token"] = payload.get("refresh_token")
    _store_tokens(
        token_payload=new_payload,
        email=token_record.get("email"),
        scopes=token_record.get("scopes", []),
    )
    if not new_payload.get("access_token"):
        raise GmailNotConnectedError("Failed to refresh Google access token.")
    return str(new_payload["access_token"])


def _header_value(headers: list[dict[str, str]], name: str) -> str | None:
    target = name.lower()
    for header in headers:
        if header.get("name", "").lower() == target:
            return header.get("value")
    return None


def _parse_email_identity(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    display_name, addr = parseaddr(value)
    return (display_name or None), (addr or None)


def _parse_received_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _decode_base64url(data: str | None) -> str:
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode(
            "utf-8", errors="replace"
        )
    except Exception:
        return ""
    return decoded


def _strip_html(text: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(re.sub(r"\s+", " ", without_tags)).strip()


def _extract_body_text(payload: dict[str, Any]) -> str:
    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {}) if isinstance(payload.get("body"), dict) else {}
    parts = payload.get("parts") if isinstance(payload.get("parts"), list) else []

    if mime_type.startswith("text/plain"):
        return _decode_base64url(body.get("data"))

    if mime_type.startswith("text/html"):
        return _strip_html(_decode_base64url(body.get("data")))

    plain_candidates: list[str] = []
    html_candidates: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        extracted = _extract_body_text(part)
        if not extracted:
            continue
        part_mime = str(part.get("mimeType", ""))
        if part_mime.startswith("text/plain"):
            plain_candidates.append(extracted)
        elif part_mime.startswith("text/html"):
            html_candidates.append(_strip_html(extracted))
        else:
            plain_candidates.append(extracted)

    if plain_candidates:
        return "\n".join(plain_candidates).strip()
    if html_candidates:
        return "\n".join(html_candidates).strip()
    return ""


def _to_summary(message: dict[str, Any]) -> GmailMessageSummary:
    payload = message.get("payload", {}) if isinstance(message.get("payload"), dict) else {}
    headers = payload.get("headers", []) if isinstance(payload.get("headers"), list) else []
    subject = _header_value(headers, "Subject")
    from_value = _header_value(headers, "From")
    from_name, from_email = _parse_email_identity(from_value)
    received_at = _parse_received_at(_header_value(headers, "Date"))
    label_ids = [str(x) for x in message.get("labelIds", [])]

    return GmailMessageSummary(
        id=str(message.get("id", "")),
        thread_id=str(message.get("threadId", "")),
        subject=subject,
        from_email=from_email,
        from_name=from_name,
        received_at=received_at,
        snippet=str(message.get("snippet", "")),
        label_ids=label_ids,
        is_unread="UNREAD" in label_ids,
    )


def list_gmail_messages(
    *,
    max_results: int = 20,
    page_token: str | None = None,
    query: str | None = None,
    label_ids: list[str] | None = None,
) -> GmailMessageListResponse:
    params: list[tuple[str, str]] = [("maxResults", str(max_results))]
    if page_token:
        params.append(("pageToken", page_token))
    if query:
        params.append(("q", query))
    for label in label_ids or ["INBOX"]:
        params.append(("labelIds", label))

    list_response = _gmail_get_json("/gmail/v1/users/me/messages", params=params)
    messages = list_response.get("messages", [])
    summaries: list[GmailMessageSummary] = []
    for message in messages:
        message_id = message.get("id")
        if not message_id:
            continue
        detail = _gmail_get_json(
            f"/gmail/v1/users/me/messages/{message_id}",
            params={
                "format": "metadata",
                "metadataHeaders": ["Subject", "From", "Date"],
            },
        )
        summaries.append(_to_summary(detail))

    return GmailMessageListResponse(
        messages=summaries,
        next_page_token=list_response.get("nextPageToken"),
        result_size_estimate=list_response.get("resultSizeEstimate"),
    )


def list_gmail_message_ids(
    *,
    max_results: int = 50,
    page_token: str | None = None,
    query: str | None = None,
    label_ids: list[str] | None = None,
) -> tuple[list[str], str | None]:
    params: list[tuple[str, str]] = [("maxResults", str(max_results))]
    if page_token:
        params.append(("pageToken", page_token))
    if query:
        params.append(("q", query))
    for label in label_ids or ["INBOX"]:
        params.append(("labelIds", label))

    list_response = _gmail_get_json("/gmail/v1/users/me/messages", params=params)
    messages = list_response.get("messages", [])
    message_ids: list[str] = []
    for message in messages:
        message_id = str(message.get("id", "")).strip()
        if message_id:
            message_ids.append(message_id)
    return message_ids, list_response.get("nextPageToken")


def get_gmail_message_detail(message_id: str) -> GmailMessageDetail:
    detail = _gmail_get_json(
        f"/gmail/v1/users/me/messages/{message_id}",
        params={"format": "full"},
    )
    payload = detail.get("payload", {}) if isinstance(detail.get("payload"), dict) else {}
    headers = payload.get("headers", []) if isinstance(payload.get("headers"), list) else []

    subject = _header_value(headers, "Subject")
    from_name, from_email = _parse_email_identity(_header_value(headers, "From"))
    _, to_email = _parse_email_identity(_header_value(headers, "To"))
    received_at = _parse_received_at(_header_value(headers, "Date"))
    label_ids = [str(x) for x in detail.get("labelIds", [])]
    body_text = _extract_body_text(payload)

    return GmailMessageDetail(
        id=str(detail.get("id", "")),
        thread_id=str(detail.get("threadId", "")),
        subject=subject,
        from_email=from_email,
        from_name=from_name,
        to_email=to_email,
        received_at=received_at,
        snippet=str(detail.get("snippet", "")),
        body_text=body_text,
        label_ids=label_ids,
        is_unread="UNREAD" in label_ids,
    )
