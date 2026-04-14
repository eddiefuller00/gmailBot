from __future__ import annotations

import math
import re
from typing import Sequence

from app.config import settings
from app.schemas import ProcessedEmail

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - runtime optional
    OpenAI = None  # type: ignore[assignment]


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0:
        return vector
    return [x / norm for x in vector]


def _hashed_embedding(text: str, dims: int = 256) -> list[float]:
    vector = [0.0] * dims
    for token in re.findall(r"[a-zA-Z0-9_]+", text.lower()):
        idx = hash(token) % dims
        vector[idx] += 1.0
    return _normalize(vector)


def embed_text(text: str) -> list[float]:
    if settings.openai_api_key and OpenAI is not None:
        try:
            client = OpenAI(api_key=settings.openai_api_key)
            result = client.embeddings.create(
                model=settings.openai_embedding_model,
                input=text,
            )
            return _normalize([float(x) for x in result.data[0].embedding])
        except Exception:
            pass
    return _hashed_embedding(text)


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

