from __future__ import annotations

import logging

from app import db
from app.config import settings

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - runtime optional
    OpenAI = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


class AIRuntimeError(RuntimeError):
    pass


class AIProcessingError(RuntimeError):
    pass


def openai_available() -> bool:
    return bool(settings.openai_api_key and OpenAI is not None)


def get_openai_client():
    if OpenAI is None:
        raise AIRuntimeError(
            "OpenAI support is unavailable because the `openai` package could not be imported."
        )
    if not settings.openai_api_key:
        raise AIRuntimeError(
            "OpenAI is required for inbox ranking and Q&A. Set `OPENAI_API_KEY`."
        )
    return OpenAI(api_key=settings.openai_api_key)


def record_ai_error(stage: str, exc: Exception) -> None:
    message = f"{stage}: {exc.__class__.__name__}: {exc}"
    logger.exception("AI processing failed during %s", stage, exc_info=exc)
    db.set_runtime_state("last_ai_error", message)


def clear_ai_error() -> None:
    db.delete_runtime_state("last_ai_error")


def raise_ai_processing_error(stage: str, exc: Exception) -> AIProcessingError:
    record_ai_error(stage, exc)
    raise AIProcessingError(
        f"OpenAI {stage} failed. Check the API key, model settings, and runtime logs."
    ) from exc
