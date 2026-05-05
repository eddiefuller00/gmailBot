from __future__ import annotations

import importlib

from app import config as config_module


def test_settings_trim_whitespace_and_normalize_empty_env(monkeypatch) -> None:
    with monkeypatch.context() as patch:
        patch.setenv("OPENAI_API_KEY", "  sk-test  ")
        patch.setenv("OPENAI_CHAT_MODEL", " gpt-5.4-mini  ")
        patch.setenv("GOOGLE_CLIENT_ID", "   ")
        patch.setenv("TOKEN_ENCRYPTION_KEY", "  secret-key  ")

        importlib.reload(config_module)

        assert config_module.settings.openai_api_key == "sk-test"
        assert config_module.settings.openai_chat_model == "gpt-5.4-mini"
        assert config_module.settings.google_client_id is None
        assert config_module.settings.token_encryption_key == "secret-key"

    importlib.reload(config_module)
