from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from functools import lru_cache

from app import db
from app.config import settings

try:
    from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError
except Exception:  # pragma: no cover - runtime optional
    OpenAI = None  # type: ignore[assignment]
    APIConnectionError = APITimeoutError = InternalServerError = RateLimitError = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)
OPENAI_MAX_RETRIES = 2
OPENAI_RETRY_BASE_DELAY_SECONDS = 0.25


class AIRuntimeError(RuntimeError):
    pass


class AIProcessingError(RuntimeError):
    pass


def openai_available() -> bool:
    return bool(settings.openai_api_key and OpenAI is not None)


@lru_cache(maxsize=1)
def _build_openai_client(api_key: str):
    return OpenAI(api_key=api_key)


def get_openai_client():
    if OpenAI is None:
        raise AIRuntimeError(
            "OpenAI support is unavailable because the `openai` package could not be imported."
        )
    if not settings.openai_api_key:
        raise AIRuntimeError(
            "OpenAI is required for inbox ranking and Q&A. Set `OPENAI_API_KEY`."
        )
    return _build_openai_client(settings.openai_api_key)


def _sanitize_error_text(text: str) -> str:
    return re.sub(r"sk-[A-Za-z0-9_-]+", "[redacted-api-key]", text)


def _is_retryable_openai_error(exc: Exception) -> bool:
    retryable_types = tuple(
        candidate
        for candidate in (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)
        if candidate is not None
    )
    if retryable_types and isinstance(exc, retryable_types):
        return True

    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int) and status_code in {408, 409, 429, 500, 502, 503, 504}:
        return True
    return False


def run_openai_request(request_fn):
    attempt = 0
    while True:
        try:
            return request_fn()
        except Exception as exc:
            if attempt >= OPENAI_MAX_RETRIES or not _is_retryable_openai_error(exc):
                raise
            delay = OPENAI_RETRY_BASE_DELAY_SECONDS * (2**attempt)
            logger.warning(
                "Retrying transient OpenAI error (%s/%s): %s",
                attempt + 1,
                OPENAI_MAX_RETRIES,
                exc.__class__.__name__,
            )
            time.sleep(delay)
            attempt += 1


def record_ai_error(stage: str, exc: Exception) -> None:
    message = _sanitize_error_text(f"{stage}: {exc.__class__.__name__}: {exc}")
    logger.exception("AI processing failed during %s", stage, exc_info=exc)
    db.set_runtime_state("last_ai_error", message)


def clear_ai_error() -> None:
    db.delete_runtime_state("last_ai_error")


def record_ai_success() -> None:
    clear_ai_error()
    db.set_runtime_state("last_ai_success_at", datetime.now(timezone.utc).isoformat())


def raise_ai_processing_error(stage: str, exc: Exception) -> AIProcessingError:
    record_ai_error(stage, exc)
    raise AIProcessingError(
        f"OpenAI {stage} failed. Check the API key, model settings, and runtime logs."
    ) from exc
