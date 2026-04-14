from __future__ import annotations

from datetime import datetime, timezone

from app.extraction import (
    _apply_profile_constraints,
    _default_summary,
    parse_llm_extraction_payload,
)
from app.prompting import build_extraction_user_payload
from app.schemas import EmailIngestItem, UserProfile


def _sample_email() -> EmailIngestItem:
    return EmailIngestItem(
        external_id="e-1",
        from_email="talent@company.com",
        from_name="Talent Team",
        subject="Interview scheduling",
        body="Please confirm your interview slot by April 20 at 5 PM.",
        received_at=datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc),
        unread=True,
    )


def test_default_summary_removes_urls() -> None:
    summary = _default_summary(
        "Job alert",
        "Apply now at https://example.com/jobs/123 and let us know.",
    )
    assert "https://example.com" not in summary
    assert summary.startswith("Job alert:")


def test_parse_llm_extraction_payload_validates_schema() -> None:
    email = _sample_email()
    parsed = parse_llm_extraction_payload(
        {
            "category": "job",
            "reason": "Recruiting email with response deadline",
            "action_required": True,
            "deadline": "2026-04-20T17:00:00Z",
            "event_date": None,
            "company": "Company",
            "summary": "Recruiter asks you to confirm your interview slot.",
        },
        email=email,
        cleaned_body=email.body,
    )
    assert parsed is not None
    assert parsed.category == "job"
    assert parsed.action_required is True
    assert parsed.deadline is not None
    assert parsed.deadline.tzinfo is not None


def test_parse_llm_extraction_payload_rejects_invalid_category() -> None:
    email = _sample_email()
    parsed = parse_llm_extraction_payload(
        {
            "category": "marketing",
            "reason": "not allowed category",
            "action_required": False,
            "deadline": None,
            "event_date": None,
            "company": None,
            "summary": "summary",
        },
        email=email,
        cleaned_body=email.body,
    )
    assert parsed is None


def test_build_extraction_user_payload_contains_modular_blocks() -> None:
    email = _sample_email()
    profile = UserProfile(priorities=["jobs"], important_senders=["recruiters"])
    payload = build_extraction_user_payload(email, email.body, profile)

    assert "rules" in payload
    assert "examples" in payload
    assert "output_schema" in payload
    assert "profile_policy" in payload
    assert payload["profile_policy"]["priority_categories"] == ["job"]
    assert payload["email"]["subject"] == "Interview scheduling"


def test_profile_constraints_reclassify_marketing_job_false_positive() -> None:
    email = EmailIngestItem(
        external_id="e-2",
        from_email="yankees@marketing.mlbemail.com",
        from_name="Yankees",
        subject="LAST CHANCE! Save 50% on Select Seats & Games",
        body="Walk-Off Offer TODAY ONLY! View online and unsubscribe below.",
        received_at=datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc),
        unread=True,
    )
    profile = UserProfile(
        role=["student", "job_seeker"],
        priorities=["jobs", "school"],
        important_senders=["recruiters", "companies"],
        deprioritize=["promotions", "newsletters"],
        highlight_deadlines=True,
    )
    parsed = parse_llm_extraction_payload(
        {
            "category": "job",
            "reason": "Contains urgent language",
            "action_required": True,
            "deadline": "2026-04-14T20:00:00Z",
            "event_date": None,
            "company": "Yankees",
            "summary": "Marketing promo.",
        },
        email=email,
        cleaned_body=email.body,
    )
    assert parsed is not None

    adjusted = _apply_profile_constraints(
        email=email,
        cleaned_body=email.body,
        metadata=parsed,
        profile=profile,
    )
    assert adjusted.category == "promotion"
    assert adjusted.action_required is False
    assert adjusted.deadline is None
