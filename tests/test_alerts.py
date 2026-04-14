from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.alerts import generate_alerts
from app.schemas import ExtractedMetadata, ProcessedEmail, UserProfile


def _build_email(
    *,
    eid: str,
    subject: str,
    from_email: str,
    category: str,
    importance: float = 8.0,
    action_required: bool = False,
    deadline: datetime | None = None,
    unread: bool = True,
) -> ProcessedEmail:
    return ProcessedEmail(
        id=int(eid.split("-")[-1]),
        external_id=eid,
        from_email=from_email,
        from_name=None,
        subject=subject,
        body=subject,
        cleaned_body=subject,
        received_at=datetime.now(timezone.utc),
        unread=unread,
        metadata=ExtractedMetadata(
            category=category,  # type: ignore[arg-type]
            importance=importance,
            reason="test",
            action_required=action_required,
            deadline=deadline,
            event_date=None,
            summary=subject,
            scoring_breakdown={},
        ),
    )


def test_alerts_prioritize_job_signals_over_promo_deadlines() -> None:
    now = datetime.now(timezone.utc)
    profile = UserProfile(
        priorities=["jobs"],
        important_senders=["recruiters"],
        deprioritize=["promotions"],
        highlight_deadlines=True,
    )

    promo = _build_email(
        eid="id-1",
        subject="LAST CHANCE! Save 50% on Select Seats",
        from_email="deals@tickets.com",
        category="promotion",
        importance=9.5,
        action_required=True,
        deadline=now + timedelta(hours=4),
    )
    job = _build_email(
        eid="id-2",
        subject="Interview scheduling",
        from_email="talent@company.com",
        category="job",
        importance=9.2,
        action_required=True,
        deadline=now + timedelta(hours=8),
    )

    alerts = generate_alerts(
        profile=profile,
        deadlines=[promo, job],
        action_required=[job],
        top_important=[promo, job],
        unread_important_count=10,
    )
    messages = [item.message.lower() for item in alerts]

    assert any("interview scheduling" in message for message in messages)
    assert all("save 50%" not in message for message in messages)


def test_alerts_respect_highlight_deadlines_flag() -> None:
    now = datetime.now(timezone.utc)
    profile = UserProfile(
        priorities=["jobs"],
        important_senders=["recruiters"],
        deprioritize=[],
        highlight_deadlines=False,
    )
    job = _build_email(
        eid="id-3",
        subject="Frontend interview follow-up needed",
        from_email="recruiter@company.com",
        category="job",
        importance=9.1,
        action_required=True,
        deadline=now + timedelta(hours=10),
    )

    alerts = generate_alerts(
        profile=profile,
        deadlines=[job],
        action_required=[job],
        top_important=[job],
        unread_important_count=5,
    )
    messages = [item.message for item in alerts]

    assert all(not message.startswith("Deadline") for message in messages)
    assert any("Job action needed:" in message for message in messages)
