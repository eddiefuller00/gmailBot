from __future__ import annotations

from datetime import datetime, timezone

from app.extraction import (
    _apply_profile_constraints,
    _default_summary,
    extract_metadata,
    _llm_extract,
    parse_llm_extraction_payload,
)
from app.prompting import (
    EMAIL_EXTRACTION_PROMPT_VERSION,
    PROCESSING_VERSION,
    build_extraction_user_payload,
    MAX_EXTRACTION_BODY_CHARS,
)
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
            "confidence": 0.97,
            "is_bulk": False,
            "action_channel": "reply",
        },
        email=email,
        cleaned_body=email.body,
    )
    assert parsed is not None
    assert parsed.category == "job"
    assert parsed.action_required is True
    assert parsed.deadline is not None
    assert parsed.deadline.tzinfo is not None
    assert parsed.confidence == 0.97
    assert parsed.prompt_version == EMAIL_EXTRACTION_PROMPT_VERSION
    assert parsed.processing_version == PROCESSING_VERSION


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
            "confidence": 0.2,
            "is_bulk": True,
            "action_channel": "none",
        },
        email=email,
        cleaned_body=email.body,
    )
    assert parsed is None


def test_build_extraction_user_payload_contains_profile_policy_and_examples() -> None:
    email = _sample_email()
    profile = UserProfile(priorities=["jobs"], important_senders=["recruiters"])
    payload = build_extraction_user_payload(email, email.body, profile)

    assert "rules" in payload
    assert "examples" in payload
    assert payload["profile_policy"]["priority_categories"] == ["job"]
    assert "profile" not in payload


def test_build_extraction_user_payload_truncates_long_body() -> None:
    email = _sample_email()
    profile = UserProfile(priorities=["jobs"])
    long_body = ("A" * 3500) + "\n\n" + ("B" * 1800)

    payload = build_extraction_user_payload(email, long_body, profile)

    body = payload["email"]["body"]
    assert len(body) <= MAX_EXTRACTION_BODY_CHARS + 10
    assert body.startswith("A" * 1200)
    assert body.endswith("B" * 500)
    assert " ... " in body


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
            "confidence": 0.61,
            "is_bulk": True,
            "action_channel": "portal",
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
    assert adjusted.action_channel == "none"
    assert adjusted.deadline is None


def test_extract_metadata_heuristic_path_marks_portal_and_bulk_signals() -> None:
    email = EmailIngestItem(
        external_id="e-3",
        from_email="no-reply@jobs.example.com",
        from_name="Updates Bot",
        subject="Application update available",
        body=(
            "Review the next step in your application here: https://example.com/app/123 "
            "This mailbox is not monitored."
        ),
        received_at=datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc),
        unread=True,
    )
    profile = UserProfile(priorities=["jobs"])

    metadata = extract_metadata(email, email.body, profile, allow_fallback=True)

    assert metadata.action_required is True
    assert metadata.action_channel == "portal"
    assert metadata.ai_source == "heuristic"


def test_extract_metadata_reclassifies_job_digest_as_newsletter() -> None:
    email = EmailIngestItem(
        external_id="e-4",
        from_email="emails@emails.efinancialcareers.com",
        from_name="eFinancialCareers",
        subject="The latest jobs picked for you!",
        body=(
            "View all jobs. You received this email because you have an account. "
            "Unsubscribe and manage your preferences."
        ),
        received_at=datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc),
        unread=True,
    )
    profile = UserProfile(priorities=["jobs"], deprioritize=["newsletters"])

    metadata = extract_metadata(email, email.body, profile, allow_fallback=True)

    assert metadata.category == "newsletter"
    assert metadata.action_required is False
    assert metadata.is_bulk is True


def test_build_extraction_user_payload_includes_profile_first_rules() -> None:
    email = _sample_email()
    payload = build_extraction_user_payload(email, email.body, UserProfile(priorities=["jobs"]))

    rules = payload["rules"]
    assert any("onboarding priorities" in rule for rule in rules)
    assert any("sender, subject, and body evidence" in rule for rule in rules)


def test_extract_metadata_reclassifies_content_digest_as_newsletter() -> None:
    email = EmailIngestItem(
        external_id="e-5",
        from_email="news@email.microsoftstart.com",
        from_name="Best of MSN",
        subject="Every TV show getting cancelled in 2026 (full list)",
        body="Read online. Best of MSN roundup. Manage your preferences.",
        received_at=datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc),
        unread=True,
    )
    profile = UserProfile(priorities=["jobs"], deprioritize=["newsletters"])

    metadata = extract_metadata(email, email.body, profile, allow_fallback=True)

    assert metadata.category == "newsletter"
    assert metadata.action_required is False
    assert metadata.is_bulk is True


def test_extract_metadata_short_circuits_obvious_bulk_without_llm(monkeypatch) -> None:
    email = EmailIngestItem(
        external_id="e-6",
        from_email="promo@tickets.com",
        from_name="Tickets",
        subject="50% off tickets tonight",
        body="Final sale ends tonight. Unsubscribe in footer.",
        received_at=datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc),
        unread=True,
    )
    profile = UserProfile(priorities=["jobs"], deprioritize=["promotions"])

    def fail_llm(*args, **kwargs):
        raise AssertionError("LLM path should not run for obvious bulk promotions")

    monkeypatch.setattr("app.extraction._llm_extract", fail_llm)

    metadata = extract_metadata(email, email.body, profile)

    assert metadata.ai_source == "heuristic"
    assert metadata.category == "promotion"
    assert metadata.action_required is False


def test_extract_metadata_short_circuits_content_digest_without_llm(monkeypatch) -> None:
    email = EmailIngestItem(
        external_id="e-7",
        from_email="news@email.microsoftstart.com",
        from_name="Best of MSN",
        subject="Every TV show getting cancelled in 2026 (full list)",
        body="Read online. Best of MSN roundup. Manage your preferences.",
        received_at=datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc),
        unread=True,
    )
    profile = UserProfile(priorities=["jobs"])

    def fail_llm(*args, **kwargs):
        raise AssertionError("LLM path should not run for obvious content digests")

    monkeypatch.setattr("app.extraction._llm_extract", fail_llm)

    metadata = extract_metadata(email, email.body, profile)

    assert metadata.ai_source == "heuristic"
    assert metadata.category == "newsletter"
    assert metadata.is_bulk is True


def test_llm_extract_falls_back_to_heuristic_on_invalid_payload(monkeypatch) -> None:
    email = _sample_email()
    profile = UserProfile(priorities=["jobs"])

    class _FakeCompletion:
        choices = [type("Choice", (), {"message": type("Message", (), {"content": '{"oops":true}'})()})()]

    class _FakeClient:
        chat = type(
            "Chat",
            (),
            {
                "completions": type(
                    "Completions",
                    (),
                    {"create": lambda *args, **kwargs: _FakeCompletion()},
                )()
            },
        )()

    monkeypatch.setattr("app.extraction.get_openai_client", lambda: _FakeClient())
    monkeypatch.setattr("app.extraction.record_ai_success", lambda: None)

    metadata = _llm_extract(email, email.body, profile)

    assert metadata.ai_source == "heuristic"
    assert "heuristic extraction was used" in metadata.reason.lower()
