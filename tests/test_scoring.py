from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.schemas import EmailIngestItem, ExtractedMetadata, UserProfile
from app.scoring import compute_importance


def test_scoring_prioritizes_job_interview_email() -> None:
    profile = UserProfile(
        role=["student", "job_seeker"],
        priorities=["jobs", "school"],
        important_senders=["recruiters"],
        deprioritize=["promotions"],
    )
    email = EmailIngestItem(
        external_id="e-1",
        from_email="talent@stripe.com",
        subject="Interview schedule - respond by April 20",
        body="Action required: please confirm your interview slot by April 20.",
        received_at=datetime.now(timezone.utc) - timedelta(hours=5),
    )
    metadata = ExtractedMetadata(
        category="job",
        action_required=True,
        deadline=datetime.now(timezone.utc) + timedelta(days=3),
        confidence=0.95,
        action_channel="reply",
    )
    score, breakdown = compute_importance(email, metadata, profile)
    assert score >= 8.0
    assert breakdown["sender_weight"] >= 8.0


def test_scoring_prioritizes_direct_interview_scheduling_from_plain_sender() -> None:
    profile = UserProfile(
        role=["student", "job_seeker"],
        priorities=["jobs", "school"],
        important_senders=["recruiters"],
        deprioritize=["promotions"],
    )
    email = EmailIngestItem(
        external_id="e-1b",
        from_email="statclass60@gmail.com",
        subject="IMPORTANT: interview scheduling",
        body=(
            "Software Engineer Inc\n\n"
            "Schedule your interview by May 5th, please pick a date between May 10th-13th."
        ),
        received_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    metadata = ExtractedMetadata(
        category="job",
        action_required=True,
        deadline=datetime.now(timezone.utc) + timedelta(days=2),
        confidence=0.95,
        action_channel="read",
    )
    score, breakdown = compute_importance(email, metadata, profile)
    assert score >= 8.0
    assert breakdown["job_specificity_adjustment"] > 0
    assert breakdown["content_evidence_adjustment"] > 0


def test_scoring_prioritizes_interview_calendar_invite_from_company_sender() -> None:
    profile = UserProfile(
        role=["student", "job_seeker"],
        priorities=["jobs"],
        important_senders=["recruiters"],
        deprioritize=["promotions"],
        highlight_deadlines=True,
    )
    email = EmailIngestItem(
        external_id="e-1c",
        from_email="michael@vibrantbt.com",
        subject="Invitation: Eddie <> Vibrant Frontend Interview @ Fri May 8, 2026 2pm - 3pm",
        body=(
            "Eddie <> Vibrant Frontend Interview\n"
            "Friday May 8, 2026 2pm - 3pm\n"
            "Join with Google Meet\n"
            "https://meet.google.com/room\n"
            "Dial-in details included."
        ),
        received_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    metadata = ExtractedMetadata(
        category="job",
        action_required=False,
        deadline=datetime.now(timezone.utc) + timedelta(days=2),
        event_date=datetime.now(timezone.utc) + timedelta(days=2, hours=1),
        confidence=0.95,
        action_channel="none",
    )

    score, breakdown = compute_importance(email, metadata, profile)

    assert score >= 8.5
    assert breakdown["job_specificity_adjustment"] > 0
    assert breakdown["content_evidence_adjustment"] > 0
    assert breakdown["job_sender_adjustment"] > 0


def test_scoring_prioritizes_short_interview_thread_confirmation() -> None:
    profile = UserProfile(
        role=["student", "job_seeker"],
        priorities=["jobs"],
        important_senders=["recruiters"],
        deprioritize=["promotions"],
    )
    email = EmailIngestItem(
        external_id="e-1d",
        from_email="michael@vibrantbt.com",
        subject="Re: Vibrant Frontend Position Follow-up",
        body=(
            "Yes, 2pm Friday works for us. Will send invite.\n\n"
            "On Mon, May 4, 2026 Michael wrote:\n"
            "We'd like to move forward with the final interview step."
        ),
        received_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    metadata = ExtractedMetadata(
        category="job",
        action_required=False,
        event_date=datetime.now(timezone.utc) + timedelta(days=2),
        confidence=0.95,
        action_channel="none",
    )

    score, breakdown = compute_importance(email, metadata, profile)

    assert score >= 8.5
    assert breakdown["job_specificity_adjustment"] > 0
    assert breakdown["content_evidence_adjustment"] > 0
    assert breakdown["job_sender_adjustment"] > 0


def test_scoring_deprioritizes_promotions() -> None:
    profile = UserProfile(priorities=["jobs"], deprioritize=["promotions"])
    email = EmailIngestItem(
        external_id="e-2",
        from_email="news@store.com",
        subject="Flash sale ends tonight",
        body="Promo discount for members.",
        received_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    metadata = ExtractedMetadata(category="promotion", action_required=False, confidence=0.95, is_bulk=True)
    score, _ = compute_importance(email, metadata, profile)
    assert score <= 5.0


def test_scoring_downranks_marketing_disguised_as_job() -> None:
    profile = UserProfile(
        priorities=["jobs", "school"],
        important_senders=["recruiters", "companies"],
        deprioritize=["promotions", "newsletters"],
        highlight_deadlines=True,
    )
    email = EmailIngestItem(
        external_id="e-3",
        from_email="yankees@marketing.mlbemail.com",
        subject="LAST CHANCE! Save 50% on Select Seats & Games",
        body=(
            "Walk-Off Offer TODAY ONLY. View online for this limited-time deal "
            "and unsubscribe below."
        ),
        received_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    metadata = ExtractedMetadata(
        category="job",
        action_required=True,
        deadline=datetime.now(timezone.utc) + timedelta(hours=8),
        confidence=0.45,
        is_bulk=True,
        action_channel="portal",
    )
    score, breakdown = compute_importance(email, metadata, profile)
    assert score <= 4.5
    assert breakdown["marketing_noise_penalty"] <= -3.0


def test_scoring_downranks_generic_job_newsletter() -> None:
    profile = UserProfile(priorities=["jobs"], deprioritize=["newsletters"])
    email = EmailIngestItem(
        external_id="e-4",
        from_email="linkedin@em.linkedin.com",
        subject="You are invited: Learn how to land a job in today's market",
        body="Career tips webinar for everyone. Unsubscribe at any time.",
        received_at=datetime.now(timezone.utc) - timedelta(hours=6),
    )
    metadata = ExtractedMetadata(
        category="job",
        action_required=True,
        confidence=0.55,
        is_bulk=True,
    )
    score, breakdown = compute_importance(email, metadata, profile)
    assert score <= 5.0
    assert breakdown["job_specificity_adjustment"] < 0


def test_scoring_sets_response_channel_signals() -> None:
    profile = UserProfile(priorities=["jobs"])
    email = EmailIngestItem(
        external_id="e-5",
        from_email="no-reply@jobs.example.com",
        subject="Application update available",
        body=(
            "Click to review your update: https://example.com/app/123 "
            "This mailbox is not monitored."
        ),
        received_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    metadata = ExtractedMetadata(category="job", action_required=True, confidence=0.8, action_channel="portal")
    _, breakdown = compute_importance(email, metadata, profile)
    assert breakdown["no_reply_sender_signal"] == 1.0
    assert breakdown["link_only_cta_signal"] == 1.0
    assert breakdown["reply_requested_signal"] == 0.0


def test_scoring_downranks_automated_job_digest_sender() -> None:
    profile = UserProfile(priorities=["jobs"], important_senders=["recruiters", "companies"])
    email = EmailIngestItem(
        external_id="e-6",
        from_email="emails@emails.efinancialcareers.com",
        subject="The latest jobs picked for you!",
        body=(
            "View all jobs. You received this email because you have an account. "
            "Manage your preferences. Unsubscribe."
        ),
        received_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    metadata = ExtractedMetadata(category="job", action_required=True, confidence=0.5, is_bulk=True)
    score, breakdown = compute_importance(email, metadata, profile)
    assert score <= 6.0
    assert breakdown["no_reply_sender_signal"] == 1.0
    assert breakdown["marketing_noise_penalty"] <= -3.0


def test_scoring_downranks_news_digest_with_candidate_language() -> None:
    profile = UserProfile(priorities=["jobs"])
    email = EmailIngestItem(
        external_id="e-7",
        from_email="eveonline@news.ccpgames.com",
        subject="Gallente Election: More Rewards, More Influence",
        body=(
            "View this message in browser. Candidate favors, and more rewards."
        ),
        received_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    metadata = ExtractedMetadata(category="job", action_required=True, confidence=0.5, is_bulk=True)
    score, breakdown = compute_importance(email, metadata, profile)
    assert score <= 5.0
    assert breakdown["marketing_noise_penalty"] <= -3.0


def test_scoring_penalizes_irrelevant_bulk_action_email_for_job_seeker() -> None:
    profile = UserProfile(
        priorities=["jobs", "school"],
        important_senders=["recruiters"],
        deprioritize=["promotions", "newsletters"],
    )
    email = EmailIngestItem(
        external_id="e-8",
        from_email="uber@uber.com",
        subject="Treat yourself with 30% convenience order!",
        body="30% off convenience items until tonight. Terms apply. Unsubscribe.",
        received_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    metadata = ExtractedMetadata(
        category="promotion",
        action_required=False,
        confidence=0.95,
        is_bulk=True,
    )

    score, breakdown = compute_importance(email, metadata, profile)

    assert score <= 3.5
    assert breakdown["profile_alignment_adjustment"] < 0
    assert breakdown["content_evidence_adjustment"] < 0
