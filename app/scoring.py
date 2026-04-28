from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from app.profile_preferences import (
    profile_deprioritize_categories,
    profile_priority_categories,
    normalize_important_sender_preferences,
)
from app.response_intent import detect_response_intent, is_no_reply_sender
from app.schemas import EmailIngestItem, ExtractedMetadata, UserProfile


URGENCY_KEYWORDS = [
    "urgent",
    "asap",
    "deadline",
    "final notice",
    "interview",
    "action required",
    "respond by",
    "today",
    "tomorrow",
]

MARKETING_TERMS = [
    "sale",
    "discount",
    "today only",
    "limited time",
    "save",
    "coupon",
    "promo",
    "unsubscribe",
    "view online",
    "% off",
]

NEWSLETTER_TERMS = [
    "newsletter",
    "digest",
    "roundup",
    "weekly",
    "you are invited",
    "learn how to",
    "view all jobs",
    "you received this email because",
    "manage your preferences",
    "daily job alerts",
]

STRONG_JOB_TERMS = [
    "application status",
    "recruiter",
    "hiring manager",
    "talent team",
    "assessment",
    "offer letter",
    "next steps",
]

CANDIDATE_CONTEXT_TERMS = [
    "interview",
    "application",
    "recruiter",
    "hiring",
    "assessment",
    "offer",
    "talent",
]

JOB_CONTEXT_TERMS = [
    "interview",
    "application",
    "recruiter",
    "hiring manager",
    "talent team",
    "talent acquisition",
    "assessment",
    "offer letter",
    "resume",
    "cv",
]

GENERIC_JOB_MARKETING_TERMS = [
    "job market",
    "career tips",
    "land a job",
    "jobs picked for you",
    "recommended jobs",
    "latest jobs picked for you",
    "may want to hire you",
    "has an open position",
    "might be right for you",
]

BULK_SENDER_TERMS = [
    "noreply",
    "no-reply",
    "alerts",
    "notifications",
    "updates",
    "digest",
    "emails",
    "newsletter",
    "marketing",
    "promo",
    "deals",
]

CONTENT_DIGEST_TERMS = [
    "view this message in browser",
    "view this email in your browser",
    "view in browser",
    "read in browser",
    "read online",
    "top stories",
    "morning briefing",
    "the morning",
    "manage your preferences",
]

CONTENT_DIGEST_SENDER_HINTS = {
    "news",
    "newsletter",
    "digest",
    "briefing",
    "updates",
    "alerts",
}


def _contains_any(text: str, terms: list[str]) -> int:
    lower = text.lower()
    return sum(1 for term in terms if _matches_term(lower, term))


def _matches_term(lower_text: str, term: str) -> bool:
    normalized = term.lower().strip()
    if not normalized:
        return False
    if re.search(r"[a-z0-9]", normalized) and " " not in normalized:
        pattern = rf"\b{re.escape(normalized)}\b"
        return bool(re.search(pattern, lower_text))
    return normalized in lower_text


def _is_bulk_sender(from_email: str) -> bool:
    lower = from_email.lower()
    return is_no_reply_sender(from_email) or any(term in lower for term in BULK_SENDER_TERMS)


def _sender_weight(from_email: str, profile: UserProfile) -> float:
    value = 3.5
    lower = from_email.lower()
    bulk_sender = _is_bulk_sender(from_email)
    preferences = normalize_important_sender_preferences(profile.important_senders)
    if not preferences:
        if bulk_sender:
            return 2.0
        return value

    if "recruiters" in preferences and any(x in lower for x in ["recruit", "talent", "hiring"]):
        value = max(value, 10.0 if not bulk_sender else 5.0)
    if "professors" in preferences and ".edu" in lower:
        value = max(value, 9.0)
    if "companies" in preferences and not bulk_sender:
        value = max(value, 8.0)

    if bulk_sender and value <= 5.0:
        value = max(2.0, value - 2.0)
    return value


def _priority_match(
    category: str,
    *,
    has_priorities: bool,
    priority_categories: set[str],
    deprioritize_categories: set[str],
) -> float:
    if category in deprioritize_categories:
        return 1.0
    if category in priority_categories:
        return 10.0
    if not has_priorities:
        return 5.0
    return 3.0


def _deprioritize_penalty(category: str, *, deprioritize_categories: set[str]) -> float:
    return -4.0 if category in deprioritize_categories else 0.0


def _urgency_score(text: str, *, category: str) -> float:
    hits = _contains_any(text, URGENCY_KEYWORDS)
    if hits == 0:
        return 2.0
    if category in {"promotion", "newsletter"}:
        return min(4.5, 2.0 + hits * 0.8)
    return min(10.0, 4.0 + hits * 2.0)


def _deadline_score(
    metadata: ExtractedMetadata,
    *,
    profile: UserProfile,
    priority_categories: set[str],
) -> float:
    if metadata.deadline:
        if metadata.category in {"promotion", "newsletter"}:
            return 2.5
        if profile.highlight_deadlines and metadata.category in priority_categories:
            return 10.0
        return 7.0 if profile.highlight_deadlines else 5.0
    if metadata.event_date:
        if metadata.category in {"promotion", "newsletter"}:
            return 2.0
        return 8.0 if metadata.category in priority_categories else 5.5
    return 1.5


def _action_required_score(
    metadata: ExtractedMetadata,
    *,
    priority_categories: set[str],
) -> float:
    if not metadata.action_required:
        return 2.0
    if metadata.category in {"promotion", "newsletter"}:
        return 1.5
    if metadata.category in priority_categories:
        return 10.0
    return 7.0


def _confidence_score(metadata: ExtractedMetadata) -> float:
    return max(1.0, min(10.0, 1.0 + metadata.confidence * 9.0))


def _bulk_penalty(metadata: ExtractedMetadata) -> float:
    if metadata.category in {"promotion", "newsletter"}:
        return -1.2
    return -1.4 if metadata.is_bulk else 0.0


def _action_channel_adjustment(metadata: ExtractedMetadata) -> float:
    if metadata.action_channel == "reply":
        return 0.9
    if metadata.action_channel == "portal":
        return 0.5
    if metadata.action_channel == "read" and metadata.action_required:
        return 0.3
    return 0.0


def _recency_score(received_at: datetime) -> float:
    now = datetime.now(timezone.utc)
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=timezone.utc)
    age = now - received_at
    if age <= timedelta(hours=24):
        return 10.0
    if age <= timedelta(days=3):
        return 7.5
    if age <= timedelta(days=7):
        return 5.0
    return 2.0


def _has_strong_job_signal(text: str, from_email: str) -> bool:
    lower = text.lower()
    if any(term in lower for term in STRONG_JOB_TERMS):
        return True
    if _matches_term(lower, "candidate") and _contains_any(lower, CANDIDATE_CONTEXT_TERMS) > 0:
        return True
    sender = from_email.lower()
    return ("recruit" in sender or "talent" in sender) and not _is_bulk_sender(from_email)


def _sender_has_content_digest_hint(from_email: str) -> bool:
    lower = from_email.lower().strip()
    local_part = lower.split("@", 1)[0]
    tokens = [token for token in re.split(r"[^a-z0-9]+", lower) if token]
    if any(token in CONTENT_DIGEST_SENDER_HINTS for token in tokens):
        return True
    return local_part.endswith("direct")


def _looks_like_content_digest(
    text: str,
    from_email: str,
    *,
    response_signals: object | None = None,
) -> bool:
    digest_hits = _contains_any(text, CONTENT_DIGEST_TERMS) + _contains_any(
        text, NEWSLETTER_TERMS
    )
    sender_hint = _sender_has_content_digest_hint(from_email)
    if digest_hits >= 2:
        return True
    if digest_hits >= 1 and (sender_hint or _is_bulk_sender(from_email)):
        return True
    if sender_hint and response_signals is not None:
        link_only_cta = getattr(response_signals, "link_only_cta", False)
        if bool(link_only_cta):
            return True
    return False


def _marketing_noise_penalty(
    email: EmailIngestItem,
    metadata: ExtractedMetadata,
    *,
    priority_categories: set[str],
    deprioritize_categories: set[str],
) -> float:
    text = f"{email.subject}\n{email.body}".lower()
    marketing_hits = _contains_any(text, MARKETING_TERMS)
    newsletter_hits = _contains_any(text, NEWSLETTER_TERMS)
    generic_job_marketing = _contains_any(text, GENERIC_JOB_MARKETING_TERMS)
    bulk_sender = _is_bulk_sender(email.from_email)
    strong_job_signal = _has_strong_job_signal(text, email.from_email)
    response_signals = detect_response_intent(
        from_email=email.from_email,
        subject=email.subject,
        body=email.body,
    )
    content_digest_like = _looks_like_content_digest(
        text,
        email.from_email,
        response_signals=response_signals,
    )
    job_context_hits = _contains_any(text, JOB_CONTEXT_TERMS)
    category = metadata.category

    penalty = 0.0
    if category in {"promotion", "newsletter"}:
        penalty -= 1.5
        if category in deprioritize_categories:
            penalty -= 1.5
        if marketing_hits >= 2 or newsletter_hits >= 2 or bulk_sender:
            penalty -= 1.0

    if category == "job" and (marketing_hits > 0 or newsletter_hits > 0 or bulk_sender):
        if not strong_job_signal:
            penalty -= 3.5
        elif generic_job_marketing > 0:
            penalty -= 2.0

    if category == "job" and not strong_job_signal and content_digest_like:
        penalty -= 3.0
    if category == "job" and not strong_job_signal and job_context_hits == 0:
        penalty -= 2.0

    if category in {"job", "school"} and newsletter_hits >= 1 and not strong_job_signal:
        penalty -= 2.0
    if response_signals.no_reply_sender:
        penalty -= 0.8
    if response_signals.link_only_cta:
        penalty -= 0.8

    if category not in priority_categories and marketing_hits >= 3:
        penalty -= 1.0

    return max(-5.0, round(penalty, 2))


def _job_specificity_adjustment(email: EmailIngestItem, metadata: ExtractedMetadata) -> float:
    if metadata.category != "job":
        return 0.0
    text = f"{email.subject}\n{email.body}".lower()
    if _has_strong_job_signal(text, email.from_email):
        return 1.2
    if _contains_any(text, GENERIC_JOB_MARKETING_TERMS) > 0:
        return -2.0
    return -0.8


def _reply_intent_adjustment(email: EmailIngestItem, metadata: ExtractedMetadata) -> float:
    if not metadata.action_required:
        return 0.0
    signals = detect_response_intent(
        from_email=email.from_email,
        subject=email.subject,
        body=email.body,
    )
    if signals.likely_needs_reply:
        return 0.4
    if signals.no_reply_sender or signals.link_only_cta:
        return -1.2
    return 0.0


def compute_importance(
    email: EmailIngestItem, metadata: ExtractedMetadata, profile: UserProfile
) -> tuple[float, dict[str, float]]:
    priority_categories = profile_priority_categories(profile)
    deprioritize_categories = profile_deprioritize_categories(profile)
    text = f"{email.subject}\n{email.body}"
    sender = _sender_weight(email.from_email, profile)
    priority = _priority_match(
        metadata.category,
        has_priorities=bool(profile.priorities),
        priority_categories=priority_categories,
        deprioritize_categories=deprioritize_categories,
    )
    urgency = _urgency_score(text, category=metadata.category)
    deadline = _deadline_score(
        metadata,
        profile=profile,
        priority_categories=priority_categories,
    )
    action = _action_required_score(
        metadata,
        priority_categories=priority_categories,
    )
    confidence = _confidence_score(metadata)
    recency = _recency_score(email.received_at)
    deprioritize_penalty = _deprioritize_penalty(
        metadata.category,
        deprioritize_categories=deprioritize_categories,
    )
    bulk_penalty = _bulk_penalty(metadata)
    noise_penalty = _marketing_noise_penalty(
        email,
        metadata,
        priority_categories=priority_categories,
        deprioritize_categories=deprioritize_categories,
    )
    job_specificity = _job_specificity_adjustment(email, metadata)
    reply_intent = _reply_intent_adjustment(email, metadata)
    action_channel = _action_channel_adjustment(metadata)
    response_signals = detect_response_intent(
        from_email=email.from_email,
        subject=email.subject,
        body=email.body,
    )

    score = (
        sender * 0.22
        + priority * 0.33
        + urgency * 0.08
        + deadline * 0.11
        + action * 0.12
        + confidence * 0.06
        + recency * 0.14
        + deprioritize_penalty
        + bulk_penalty
        + noise_penalty
        + job_specificity
        + reply_intent
        + action_channel
    )
    score = max(1.0, min(10.0, round(score, 2)))
    breakdown = {
        "sender_weight": round(sender, 2),
        "priority_match": round(priority, 2),
        "urgency": round(urgency, 2),
        "deadline_presence": round(deadline, 2),
        "action_required": round(action, 2),
        "confidence": round(confidence, 2),
        "recency": round(recency, 2),
        "deprioritize_penalty": round(deprioritize_penalty, 2),
        "bulk_penalty": round(bulk_penalty, 2),
        "marketing_noise_penalty": round(noise_penalty, 2),
        "job_specificity_adjustment": round(job_specificity, 2),
        "reply_intent_adjustment": round(reply_intent, 2),
        "action_channel_adjustment": round(action_channel, 2),
        "no_reply_sender_signal": 1.0 if response_signals.no_reply_sender else 0.0,
        "link_only_cta_signal": 1.0 if response_signals.link_only_cta else 0.0,
        "reply_requested_signal": 1.0 if response_signals.likely_needs_reply else 0.0,
        "final_score": score,
    }
    return score, breakdown
