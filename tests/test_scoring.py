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
    )
    score, breakdown = compute_importance(email, metadata, profile)
    assert score >= 8.0
    assert breakdown["sender_weight"] >= 8.0


def test_scoring_deprioritizes_promotions() -> None:
    profile = UserProfile(priorities=["jobs"], deprioritize=["promotions"])
    email = EmailIngestItem(
        external_id="e-2",
        from_email="news@store.com",
        subject="Flash sale ends tonight",
        body="Promo discount for members.",
        received_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    metadata = ExtractedMetadata(category="promotion", action_required=False)
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
    )
    score, breakdown = compute_importance(email, metadata, profile)
    assert score <= 5.0
    assert breakdown["job_specificity_adjustment"] < 0
