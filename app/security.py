from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


@lru_cache(maxsize=1)
def _fernet() -> Fernet | None:
    if not settings.token_encryption_key:
        return None
    return Fernet(settings.token_encryption_key.encode("utf-8"))


def token_encryption_enabled() -> bool:
    return _fernet() is not None


def serialize_token_payload(payload: dict[str, Any]) -> tuple[str, bool]:
    plain = json.dumps(payload)
    cipher = _fernet()
    if cipher is None:
        if not settings.allow_insecure_token_storage:
            raise RuntimeError(
                "TOKEN_ENCRYPTION_KEY is required when ALLOW_INSECURE_TOKEN_STORAGE is false."
            )
        return plain, False
    return cipher.encrypt(plain.encode("utf-8")).decode("utf-8"), True


def deserialize_token_payload(token_data: str, is_encrypted: bool) -> dict[str, Any]:
    if not is_encrypted:
        return json.loads(token_data)

    cipher = _fernet()
    if cipher is None:
        raise RuntimeError(
            "Encrypted Google token was found, but TOKEN_ENCRYPTION_KEY is not set."
        )

    try:
        decrypted = cipher.decrypt(token_data.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Failed to decrypt Google token payload.") from exc
    return json.loads(decrypted)

