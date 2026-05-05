from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from typing import Sequence

from app.ai_runtime import get_openai_client, raise_ai_processing_error, record_ai_success, run_openai_request
from app.config import settings
from app.schemas import ProcessedEmail


EMBEDDING_MAX_CHARS = 2800
EMBEDDING_HEAD_CHARS = 1900
EMBEDDING_TAIL_CHARS = 700
QUERY_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "do",
    "does",
    "first",
    "for",
    "from",
    "have",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "needs",
    "of",
    "on",
    "or",
    "reply",
    "the",
    "this",
    "to",
    "what",
    "when",
    "which",
    "who",
    "with",
}


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0:
        return vector
    return [x / norm for x in vector]


def _prepare_embedding_input(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= EMBEDDING_MAX_CHARS:
        return normalized

    head = normalized[:EMBEDDING_HEAD_CHARS].rstrip()
    tail = normalized[-EMBEDDING_TAIL_CHARS :].lstrip()
    return f"{head} ... {tail}"


def embed_text(text: str) -> list[float]:
    try:
        client = get_openai_client()
        result = run_openai_request(
            lambda: client.embeddings.create(
                model=settings.openai_embedding_model,
                input=_prepare_embedding_input(text),
            )
        )
        record_ai_success()
        return _normalize([float(x) for x in result.data[0].embedding])
    except Exception as exc:
        raise_ai_processing_error("embedding", exc)


def cosine_similarity(v1: Sequence[float], v2: Sequence[float]) -> float:
    if not v1 or not v2:
        return 0.0
    n = min(len(v1), len(v2))
    return float(sum(v1[i] * v2[i] for i in range(n)))


def _query_terms(query: str) -> list[str]:
    terms = re.findall(r"[a-z0-9]+", query.lower())
    return [term for term in terms if len(term) >= 3 and term not in QUERY_STOPWORDS]


def _keyword_overlap_bonus(query_terms: list[str], email: ProcessedEmail) -> float:
    if not query_terms:
        return 0.0
    haystack = " ".join(
        [
            email.subject.lower(),
            email.from_email.lower(),
            email.metadata.summary.lower(),
            email.metadata.reason.lower(),
        ]
    )
    hits = sum(1 for term in query_terms if re.search(rf"\b{re.escape(term)}\b", haystack))
    return min(0.18, hits * 0.06)


def _metadata_bonus(email: ProcessedEmail) -> float:
    bonus = 0.0
    bonus += min(0.2, max(0.0, email.metadata.importance) / 50.0)
    if email.unread:
        bonus += 0.05
    if email.metadata.action_required:
        bonus += 0.08
    if email.metadata.category in {"job", "school", "bill", "event"}:
        bonus += 0.03
    if email.metadata.is_bulk:
        bonus -= 0.12
    if email.metadata.category in {"promotion", "newsletter"}:
        bonus -= 0.08

    now = datetime.now(timezone.utc)
    received_at = email.received_at
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=timezone.utc)
    age = now - received_at
    if age <= timedelta(days=3):
        bonus += 0.04
    elif age > timedelta(days=30):
        bonus -= 0.05

    if email.metadata.deadline is not None:
        deadline = email.metadata.deadline
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if now <= deadline <= now + timedelta(days=7):
            bonus += 0.08

    if email.metadata.event_date is not None:
        event_date = email.metadata.event_date
        if event_date.tzinfo is None:
            event_date = event_date.replace(tzinfo=timezone.utc)
        if now <= event_date <= now + timedelta(days=7):
            bonus += 0.05

    return bonus


def semantic_rank(
    query: str,
    email_vectors: list[tuple[ProcessedEmail, list[float]]],
    limit: int = 8,
) -> list[ProcessedEmail]:
    q = embed_text(query)
    query_terms = _query_terms(query)
    scored = [
        (
            email,
            cosine_similarity(q, vector)
            + _keyword_overlap_bonus(query_terms, email)
            + _metadata_bonus(email),
        )
        for (email, vector) in email_vectors
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    return [item[0] for item in scored[:limit]]
