from __future__ import annotations

import math
import re
from typing import Sequence

from app.ai_runtime import clear_ai_error, get_openai_client, raise_ai_processing_error
from app.config import settings
from app.schemas import ProcessedEmail


EMBEDDING_MAX_CHARS = 10000
EMBEDDING_HEAD_CHARS = 6000
EMBEDDING_TAIL_CHARS = 3500


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
        result = client.embeddings.create(
            model=settings.openai_embedding_model,
            input=_prepare_embedding_input(text),
        )
        clear_ai_error()
        return _normalize([float(x) for x in result.data[0].embedding])
    except Exception as exc:
        raise_ai_processing_error("embedding", exc)


def cosine_similarity(v1: Sequence[float], v2: Sequence[float]) -> float:
    if not v1 or not v2:
        return 0.0
    n = min(len(v1), len(v2))
    return float(sum(v1[i] * v2[i] for i in range(n)))


def semantic_rank(
    query: str,
    email_vectors: list[tuple[ProcessedEmail, list[float]]],
    limit: int = 8,
) -> list[ProcessedEmail]:
    q = embed_text(query)
    scored = [
        (email, cosine_similarity(q, vector)) for (email, vector) in email_vectors
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    return [item[0] for item in scored[:limit]]
