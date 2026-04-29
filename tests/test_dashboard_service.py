from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import service
from app.profile_preferences import profile_processing_fingerprint
from app.schemas import ExtractedMetadata, ProcessedEmail, UserProfile


def _build_email(
    *,
    eid: str,
    subject: str,
    from_email: str,
    category: str,
    importance: float,
    action_required: bool = False,
    deadline: datetime | None = None,
    is_bulk: bool = False,
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
        unread=True,
        metadata=ExtractedMetadata(
            category=category,  # type: ignore[arg-type]
            importance=importance,
            reason="test",
            action_required=action_required,
            deadline=deadline,
            event_date=None,
            summary=subject,
            confidence=0.9,
            is_bulk=is_bulk,
            scoring_breakdown={},
        ),
    )


def test_build_dashboard_filters_irrelevant_bulk_priority_items(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    profile = UserProfile(
        priorities=["jobs"],
        important_senders=["recruiters"],
        deprioritize=["promotions", "newsletters"],
    )
    promo_deadline = _build_email(
        eid="id-1",
        subject="Treat yourself with 30% convenience order!",
        from_email="uber@uber.com",
        category="promotion",
        importance=9.1,
        action_required=True,
        deadline=now + timedelta(hours=8),
        is_bulk=True,
    )
    digest_action = _build_email(
        eid="id-2",
        subject="Every TV show getting cancelled in 2026 (full list)",
        from_email="news@email.microsoftstart.com",
        category="job",
        importance=8.9,
        action_required=True,
        is_bulk=True,
    )
    real_job = _build_email(
        eid="id-3",
        subject="Interview scheduling",
        from_email="talent@company.com",
        category="job",
        importance=9.4,
        action_required=True,
        deadline=now + timedelta(days=1),
    )

    monkeypatch.setattr(service.db, "get_profile", lambda: profile)
    monkeypatch.setattr(service, "refresh_profile_scores", lambda profile, limit=200: 0)
    monkeypatch.setattr(service.db, "list_top_important", lambda limit: [promo_deadline, digest_action, real_job])
    monkeypatch.setattr(service.db, "list_with_deadlines", lambda limit: [promo_deadline, real_job])
    monkeypatch.setattr(service.db, "list_with_events", lambda limit: [])
    monkeypatch.setattr(service.db, "list_by_category", lambda category, limit=20: [digest_action, real_job])
    monkeypatch.setattr(service.db, "list_action_required", lambda limit: [digest_action, promo_deadline, real_job])

    dashboard = service.build_dashboard(top_n=3)

    assert [email.subject for email in dashboard.top_important_emails] == ["Interview scheduling"]
    assert [email.subject for email in dashboard.upcoming_deadlines] == ["Interview scheduling"]
    assert [email.subject for email in dashboard.action_required] == []


def test_refresh_profile_scores_recomputes_stale_rows_without_ai(monkeypatch) -> None:
    profile = UserProfile(priorities=["jobs"], important_senders=["recruiters"])
    stale = _build_email(
        eid="id-4",
        subject="Interview scheduling",
        from_email="talent@company.com",
        category="job",
        importance=4.0,
        action_required=True,
    )
    stale.body = "Please confirm your interview slot by tomorrow."
    stale.cleaned_body = stale.body
    stale.received_at = datetime.now(timezone.utc) - timedelta(hours=2)
    stale.metadata.profile_fingerprint = "old-profile"

    monkeypatch.setattr(
        service.db,
        "list_profile_stale_processed_emails",
        lambda **kwargs: [stale],
    )

    updates: list[dict[str, object]] = []
    monkeypatch.setattr(
        service.db,
        "update_processed_email_scoring",
        lambda **kwargs: updates.append(kwargs),
    )

    refreshed = service.refresh_profile_scores(profile, limit=20)

    assert refreshed == 1
    assert updates
    assert updates[0]["external_id"] == stale.external_id
    assert updates[0]["profile_fingerprint"] == profile_processing_fingerprint(profile)
    assert float(updates[0]["importance"]) > 4.0


def test_build_dashboard_excludes_smoke_rows_when_gmail_connected(monkeypatch) -> None:
    profile = UserProfile(priorities=["jobs"])
    smoke = _build_email(
        eid="id-9",
        subject="Interview scheduling",
        from_email="talent@example.com",
        category="job",
        importance=9.9,
        action_required=True,
    )
    smoke.external_id = "smoke-1"
    real = _build_email(
        eid="id-10",
        subject="Real Gmail application update",
        from_email="talent@company.com",
        category="job",
        importance=9.1,
        action_required=True,
    )
    real.external_id = "gmail:abc123"

    monkeypatch.setattr(service.db, "get_profile", lambda: profile)
    monkeypatch.setattr(service.db, "get_google_oauth_token", lambda: {"email": "user@example.com"})
    monkeypatch.setattr(service.db, "delete_sample_emails", lambda: 1)
    monkeypatch.setattr(service, "refresh_profile_scores", lambda profile, limit=200: 0)
    monkeypatch.setattr(service.db, "list_top_important", lambda limit: [smoke, real])
    monkeypatch.setattr(service.db, "list_with_deadlines", lambda limit: [])
    monkeypatch.setattr(service.db, "list_with_events", lambda limit: [])
    monkeypatch.setattr(service.db, "list_by_category", lambda category, limit=20: [smoke, real])
    monkeypatch.setattr(service.db, "list_action_required", lambda limit: [smoke, real])

    dashboard = service.build_dashboard(top_n=5)

    subjects = [email.subject for email in dashboard.top_important_emails]
    assert subjects == ["Real Gmail application update"]
