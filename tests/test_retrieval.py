from __future__ import annotations

from app import retrieval


def test_prepare_embedding_input_normalizes_whitespace_without_truncation() -> None:
    prepared = retrieval._prepare_embedding_input("Subject\n\nBody\twith   spacing")

    assert prepared == "Subject Body with spacing"


def test_prepare_embedding_input_truncates_long_text_and_keeps_head_and_tail() -> None:
    prefix = "A" * (retrieval.EMBEDDING_HEAD_CHARS + 500)
    suffix = "B" * (retrieval.EMBEDDING_TAIL_CHARS + 500)

    prepared = retrieval._prepare_embedding_input(f"{prefix} {suffix}")

    assert len(prepared) <= retrieval.EMBEDDING_MAX_CHARS + 10
    assert prepared.startswith("A" * retrieval.EMBEDDING_HEAD_CHARS)
    assert prepared.endswith("B" * retrieval.EMBEDDING_TAIL_CHARS)
    assert " ... " in prepared
