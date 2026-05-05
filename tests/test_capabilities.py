from __future__ import annotations

from types import SimpleNamespace

from app import capabilities


def test_get_capabilities_reports_unverified_openai_runtime(monkeypatch) -> None:
    monkeypatch.setattr(
        capabilities,
        "settings",
        SimpleNamespace(
            openai_api_key="sk-test",
            google_client_id=None,
            google_client_secret=None,
            google_redirect_uri=None,
            token_encryption_key=None,
        ),
    )
    monkeypatch.setattr(capabilities, "openai_available", lambda: True)
    monkeypatch.setattr(capabilities, "token_encryption_enabled", lambda: False)
    monkeypatch.setattr(
        capabilities.db,
        "get_runtime_state",
        lambda key: None,
    )

    response = capabilities.get_capabilities()

    assert response.openai.available is True
    assert "not completed a successful model call yet" in response.openai.message


def test_get_capabilities_reports_last_runtime_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        capabilities,
        "settings",
        SimpleNamespace(
            openai_api_key="sk-test",
            google_client_id="google-id",
            google_client_secret="google-secret",
            google_redirect_uri="http://localhost/callback",
            token_encryption_key="token-key",
        ),
    )
    monkeypatch.setattr(capabilities, "openai_available", lambda: True)
    monkeypatch.setattr(capabilities, "token_encryption_enabled", lambda: True)

    runtime_state = {
        "last_ai_error": {"key": "last_ai_error", "value": "bad auth", "updated_at": None},
        "last_ai_success_at": None,
        "last_successful_sync_at": None,
    }
    monkeypatch.setattr(
        capabilities.db,
        "get_runtime_state",
        lambda key: runtime_state.get(key),
    )

    response = capabilities.get_capabilities()

    assert response.openai.available is True
    assert "last runtime call failed" in response.openai.message
    assert response.last_ai_error == "bad auth"

