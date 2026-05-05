from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import retrieval
from app.schemas import ExtractedMetadata, ProcessedEmail


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


def test_semantic_rank_prefers_actionable_priority_email_over_newsletter(monkeypatch) -> None:
    monkeypatch.setattr(retrieval, "embed_text", lambda query: [1.0, 0.0])
    now = datetime.now(timezone.utc)
    urgent_job = ProcessedEmail(
        id=1,
        external_id="gmail:1",
        from_email="talent@company.com",
        from_name="Talent Team",
        subject="Interview scheduling",
        body="Please confirm your interview slot.",
        cleaned_body="Please confirm your interview slot.",
        received_at=now,
        unread=True,
        metadata=ExtractedMetadata(
            category="job",
            importance=9.4,
            reason="Recruiter requested a direct reply.",
            action_required=True,
            deadline=now + timedelta(days=2),
            summary="Recruiter asks the user to confirm an interview slot.",
            confidence=0.95,
            is_bulk=False,
            action_channel="reply",
        ),
    )
    newsletter = ProcessedEmail(
        id=2,
        external_id="gmail:2",
        from_email="news@company.com",
        from_name="News",
        subject="Weekly newsletter",
        body="Weekly roundup",
        cleaned_body="Weekly roundup",
        received_at=now,
        unread=True,
        metadata=ExtractedMetadata(
            category="newsletter",
            importance=4.0,
            reason="Automated digest.",
            action_required=False,
            summary="Weekly company newsletter.",
            confidence=0.9,
            is_bulk=True,
            action_channel="none",
        ),
    )

    ranked = retrieval.semantic_rank(
        "What needs my reply first?",
        [(newsletter, [1.0, 0.0]), (urgent_job, [1.0, 0.0])],
        limit=2,
    )

    assert [email.external_id for email in ranked] == ["gmail:1", "gmail:2"]
