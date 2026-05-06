from __future__ import annotations

import pytest

from app import gmail_integration


class _FakeResponse:
    def __init__(self, *, status_code: int, payload: dict[str, object], text: str) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def post(self, url: str, data: dict[str, object], headers: dict[str, str]) -> _FakeResponse:
        return self.response


def test_refresh_access_token_invalid_grant_clears_connection(monkeypatch) -> None:
    response = _FakeResponse(
        status_code=400,
        payload={
            "error": "invalid_grant",
            "error_description": "Token has been expired or revoked.",
        },
        text='{"error":"invalid_grant"}',
    )
    cleared = {"token": 0, "cursor": 0}

    monkeypatch.setattr(gmail_integration, "_require_google_oauth_config", lambda: None)
    monkeypatch.setattr(gmail_integration, "_require_encrypted_token_storage", lambda: None)
    monkeypatch.setattr(
        gmail_integration.httpx,
        "Client",
        lambda timeout=30.0: _FakeClient(response),
    )
    monkeypatch.setattr(
        gmail_integration.db,
        "clear_google_oauth_token",
        lambda: cleared.__setitem__("token", cleared["token"] + 1),
    )
    monkeypatch.setattr(
        gmail_integration.db,
        "delete_gmail_sync_cursor",
        lambda scope_key=None: cleared.__setitem__("cursor", cleared["cursor"] + 1),
    )

    with pytest.raises(
        gmail_integration.GmailNotConnectedError,
        match="Google connection expired or was revoked.",
    ):
        gmail_integration._refresh_access_token("refresh-token")

    assert cleared == {"token": 1, "cursor": 1}


def test_http_post_form_prefers_google_error_description(monkeypatch) -> None:
    response = _FakeResponse(
        status_code=401,
        payload={
            "error": "invalid_client",
            "error_description": "Client authentication failed.",
        },
        text='{"error":"invalid_client"}',
    )

    monkeypatch.setattr(
        gmail_integration.httpx,
        "Client",
        lambda timeout=30.0: _FakeClient(response),
    )

    with pytest.raises(
        gmail_integration.GoogleOAuthFlowError,
        match="Client authentication failed.",
    ):
        gmail_integration._http_post_form("https://oauth.example/token", {})
