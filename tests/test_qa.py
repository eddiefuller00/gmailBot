from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.qa import answer_query
from app.schemas import ExtractedMetadata, ProcessedEmail


def _make_email(
    *,
    eid: str,
    subject: str,
    from_email: str,
    category: str,
    action_required: bool = False,
    deadline: datetime | None = None,
    event_date: datetime | None = None,
) -> ProcessedEmail:
    return ProcessedEmail(
        id=1,
        external_id=eid,
        from_email=from_email,
        from_name=None,
        subject=subject,
        body=subject,
        cleaned_body=subject,
        received_at=datetime.now(timezone.utc),
        unread=True,
        metadata=ExtractedMetadata(
            category=category,  # type: ignore[arg-type]
            importance=9.0,
            reason="test",
            action_required=action_required,
            deadline=deadline,
            event_date=event_date,
            summary=subject,
        ),
    )


def test_qa_deadline_query() -> None:
    soon = datetime.now(timezone.utc) + timedelta(days=2)
    emails = [
        _make_email(
            eid="1",
            subject="Interview scheduling",
            from_email="talent@company.com",
            category="job",
            action_required=True,
            deadline=soon,
        ),
        _make_email(
            eid="2",
            subject="Weekly newsletter",
            from_email="news@company.com",
            category="newsletter",
        ),
    ]
    answer, supporting = answer_query("What deadlines do I have this week?", emails)
    assert "coming up this week" in answer.lower()
    assert len(supporting) == 1

