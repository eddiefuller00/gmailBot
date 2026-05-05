from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from dateutil import parser as date_parser
from pydantic import BaseModel, ValidationError

from app.ai_runtime import get_openai_client, raise_ai_processing_error, record_ai_success, run_openai_request
from app.config import settings
from app.profile_preferences import (
    profile_deprioritize_categories,
    profile_priority_categories,
)
from app.prompting import (
    EMAIL_EXTRACTION_PROMPT_VERSION,
    EMAIL_EXTRACTION_SYSTEM_PROMPT,
    PROCESSING_VERSION,
    build_extraction_user_payload,
)
from app.response_intent import (
    ResponseIntentSignals,
    derive_action_channel,
    detect_response_intent,
    is_no_reply_sender,
)
from app.schemas import ActionChannel, Category, EmailIngestItem, ExtractedMetadata, UserProfile


EXTRACTION_MAX_COMPLETION_TOKENS = 220
logger = logging.getLogger(__name__)


CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "job": [
        "interview",
        "recruiter",
        "application",
        "offer",
        "internship",
        "hiring",
        "assessment",
    ],
    "school": [
        "assignment",
        "course",
        "professor",
        "campus",
        "syllabus",
        "exam",
        "homework",
        "tuition",
        "registrar",
    ],
    "bill": [
        "invoice",
        "payment",
        "bill",
        "due",
        "statement",
        "subscription",
        "renewal",
    ],
    "event": ["event", "webinar", "meeting", "calendar", "workshop", "invite"],
    "promotion": ["sale", "discount", "offer ends", "promo", "coupon"],
    "newsletter": ["newsletter", "weekly digest", "roundup", "update"],
    "personal": ["dad", "mom", "friend", "family", "dinner", "weekend"],
}

ACTION_KEYWORDS = [
    "please respond",
    "reply by",
    "confirm",
    "complete",
    "submit",
    "action required",
    "register",
    "schedule",
    "log in",
    "review",
]

MARKETING_TERMS = [
    "sale",
    "discount",
    "offer ends",
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
    "weekly update",
    "weekly digest",
    "daily job alerts",
    "jobs picked for you",
    "recommended for you",
    "view all jobs",
    "you received this email because",
    "manage your preferences",
]

GENERIC_JOB_MARKETING_TERMS = [
    "jobs picked for you",
    "recommended for you",
    "recommended jobs",
    "latest jobs",
    "view all jobs",
    "daily job alerts",
]

CONTENT_DIGEST_TERMS = [
    "view this email in your browser",
    "view in browser",
    "read online",
    "read in browser",
    "top stories",
    "morning briefing",
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

SCHOOL_CONTEXT_TERMS = [
    "school",
    "college",
    "university",
    "course",
    "professor",
    "campus",
    "syllabus",
    "homework",
    "assignment",
    "registrar",
    "tuition",
]

BILL_CONTEXT_TERMS = [
    "invoice",
    "payment due",
    "balance due",
    "amount due",
    "statement available",
    "autopay",
    "past due",
    "charged",
    "receipt",
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

DEADLINE_MARKERS = [
    r"(?:deadline|due|respond by|reply by|submit by)\s*[:\-]?\s*([A-Za-z0-9,\-\/: ]+)",
    r"by\s+([A-Za-z]{3,9}\s+\d{1,2}(?:,\s*\d{4})?(?:\s+\d{1,2}:\d{2}\s*(?:am|pm))?)",
]

EVENT_MARKERS = [
    r"(?:interview|meeting|event|webinar|office hours|dinner)\s*(?:on|at)?\s*([A-Za-z]{3,9}\s+\d{1,2}(?:,\s*\d{4})?(?:\s+\d{1,2}:\d{2}\s*(?:am|pm))?)",
    r"(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2})",
]


def _default_summary(subject: str, body: str) -> str:
    without_urls = re.sub(r"https?://\S+", "", body, flags=re.IGNORECASE)
    stripped = re.sub(r"\s+", " ", without_urls).strip()
    if not stripped:
        return subject
    head = stripped[:220]
    return f"{subject}: {head}" if subject else head


def _matches_term(lower_text: str, term: str) -> bool:
    normalized = term.lower().strip()
    if not normalized:
        return False
    if re.search(r"[a-z0-9]", normalized) and " " not in normalized:
        pattern = rf"\b{re.escape(normalized)}\b"
        return bool(re.search(pattern, lower_text))
    return normalized in lower_text


def _contains_any(text: str, terms: list[str]) -> bool:
    lower = text.lower()
    return any(_matches_term(lower, term) for term in terms)


def _count_any(text: str, terms: list[str]) -> int:
    lower = text.lower()
    return sum(1 for term in terms if _matches_term(lower, term))


def _extract_datetime(text: str, markers: list[str]) -> datetime | None:
    for pattern in markers:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            candidate = match.group(1).strip()
            try:
                parsed = date_parser.parse(candidate, fuzzy=True)
            except Exception:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
    return None


def _extract_company(from_email: str, subject: str, body: str) -> str | None:
    domain = from_email.split("@")[-1].lower()
    if domain.endswith(".edu"):
        return None
    core = domain.split(".")[0]
    if core and core not in {"gmail", "outlook", "yahoo", "hotmail"}:
        return core.capitalize()

    match = re.search(r"\b(?:at|from)\s+([A-Z][A-Za-z0-9&\.\-]+)", f"{subject} {body}")
    if match:
        return match.group(1)
    return None


def _is_bulk_sender(from_email: str) -> bool:
    lower = from_email.lower()
    return is_no_reply_sender(from_email) or any(term in lower for term in BULK_SENDER_TERMS)


def _sender_has_content_digest_hint(from_email: str) -> bool:
    lower = from_email.lower().strip()
    local_part = lower.split("@", 1)[0]
    tokens = [token for token in re.split(r"[^a-z0-9]+", lower) if token]
    return local_part.endswith("direct") or any(
        token in CONTENT_DIGEST_SENDER_HINTS for token in tokens
    )


def _looks_like_content_digest(text: str, from_email: str) -> bool:
    digest_hits = _count_any(text, CONTENT_DIGEST_TERMS) + _count_any(text, NEWSLETTER_TERMS)
    if digest_hits >= 2:
        return True
    if digest_hits >= 1 and (_sender_has_content_digest_hint(from_email) or _is_bulk_sender(from_email)):
        return True
    return False


def _looks_like_generic_job_digest(text: str, from_email: str) -> bool:
    job_marketing_hits = _count_any(text, GENERIC_JOB_MARKETING_TERMS)
    if job_marketing_hits == 0:
        return False
    return _is_bulk_sender(from_email) or not _strong_job_signal(text, from_email)


def _append_reason(reason: str, message: str) -> str:
    base = reason.strip()
    if not base:
        return message
    if message.lower() in base.lower():
        return base
    return f"{base}; {message}"


def _pick_category(text: str) -> Category:
    lower = text.lower()
    scores: dict[str, int] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        scores[category] = sum(1 for keyword in keywords if _matches_term(lower, keyword))
    if scores.get("school", 0) > 0 and not _contains_any(lower, SCHOOL_CONTEXT_TERMS):
        scores["school"] = 0
    if scores.get("bill", 0) > 0 and not _contains_any(lower, BILL_CONTEXT_TERMS):
        scores["bill"] = max(0, scores["bill"] - 1)
    best = max(scores.items(), key=lambda kv: kv[1])
    return best[0] if best[1] > 0 else "other"  # type: ignore[return-value]


def _strong_job_signal(text: str, from_email: str) -> bool:
    lower = text.lower()
    if _contains_any(lower, JOB_CONTEXT_TERMS):
        return True
    return ("recruit" in from_email.lower() or "talent" in from_email.lower()) and not _is_bulk_sender(
        from_email
    )


def _apply_profile_constraints(
    *,
    email: EmailIngestItem,
    cleaned_body: str,
    metadata: ExtractedMetadata,
    profile: UserProfile,
) -> ExtractedMetadata:
    adjusted = metadata.model_copy(deep=True)
    text = f"{email.subject}\n{cleaned_body}".lower()
    priority_categories = profile_priority_categories(profile)
    deprioritized_categories = profile_deprioritize_categories(profile)
    strong_job_signal = _strong_job_signal(text, email.from_email)
    marketing_like = _contains_any(text, MARKETING_TERMS)
    newsletter_like = _contains_any(text, NEWSLETTER_TERMS)
    school_context = _contains_any(text, SCHOOL_CONTEXT_TERMS)
    bill_context = _contains_any(text, BILL_CONTEXT_TERMS)

    if adjusted.category == "job" and not strong_job_signal and (marketing_like or newsletter_like):
        adjusted.category = "newsletter" if newsletter_like else "promotion"
        adjusted.action_required = False
        adjusted.action_channel = "none"
        adjusted.deadline = None
        adjusted.event_date = None
        adjusted.is_bulk = True
        adjusted.reason = _append_reason(
            adjusted.reason,
            f"Reclassified as {adjusted.category} because this looks automated rather than candidacy-specific",
        )

    if adjusted.category == "school" and not school_context and (marketing_like or newsletter_like):
        adjusted.category = "promotion" if marketing_like else "newsletter"
        adjusted.action_required = False
        adjusted.action_channel = "none"
        adjusted.deadline = None
        adjusted.event_date = None
        adjusted.is_bulk = True
        adjusted.reason = _append_reason(
            adjusted.reason,
            "Reclassified because there is no direct academic context",
        )

    if adjusted.category == "bill" and not bill_context and newsletter_like:
        adjusted.category = "newsletter"
        adjusted.action_required = False
        adjusted.action_channel = "none"
        adjusted.deadline = None
        adjusted.event_date = None
        adjusted.is_bulk = True
        adjusted.reason = _append_reason(
            adjusted.reason,
            "Reclassified because this is a digest rather than a billing workflow",
        )

    if adjusted.category in {"promotion", "newsletter"} and adjusted.category in deprioritized_categories:
        adjusted.reason = _append_reason(adjusted.reason, "Matches the user's deprioritized categories")

    if adjusted.category in priority_categories and not adjusted.action_required and adjusted.action_channel == "none":
        adjusted.action_channel = "read"

    return adjusted


def _apply_response_intent_signals(
    *,
    email: EmailIngestItem,
    cleaned_body: str,
    metadata: ExtractedMetadata,
) -> ExtractedMetadata:
    adjusted = metadata.model_copy(deep=True)
    signals = detect_response_intent(
        from_email=email.from_email,
        subject=email.subject,
        body=cleaned_body,
    )

    adjusted.is_bulk = adjusted.is_bulk or _is_bulk_sender(email.from_email)
    adjusted.action_channel = derive_action_channel(
        action_required=adjusted.action_required,
        signals=signals,
    )

    if signals.no_reply_sender:
        adjusted.reason = _append_reason(adjusted.reason, "Sender appears to be automated or no-reply")
    if signals.link_only_cta and adjusted.action_channel == "portal":
        adjusted.reason = _append_reason(adjusted.reason, "Action is likely completed through a portal or link")
    if signals.likely_needs_reply:
        adjusted.reason = _append_reason(adjusted.reason, "Direct reply requested")

    if adjusted.category in {"promotion", "newsletter"}:
        adjusted.action_required = False
        adjusted.action_channel = "none"
        adjusted.is_bulk = True

    return adjusted


def _heuristic_extract(email: EmailIngestItem, cleaned_body: str) -> ExtractedMetadata:
    text = f"{email.subject}\n{cleaned_body}"
    lower_text = text.lower()
    signals = detect_response_intent(
        from_email=email.from_email,
        subject=email.subject,
        body=cleaned_body,
    )
    action_required = any(token in lower_text for token in ACTION_KEYWORDS)
    if action_required and not signals.likely_needs_reply and (
        signals.no_reply_sender or signals.link_only_cta
    ):
        action_required = True

    digest_like = _looks_like_content_digest(lower_text, email.from_email)
    generic_job_digest = _looks_like_generic_job_digest(lower_text, email.from_email)
    is_bulk = (
        _is_bulk_sender(email.from_email)
        or digest_like
        or generic_job_digest
        or _contains_any(text, NEWSLETTER_TERMS + MARKETING_TERMS)
    )
    category = _pick_category(text)
    if digest_like or generic_job_digest:
        category = "newsletter"
    if is_bulk and category in {"job", "school", "bill", "other"} and not _strong_job_signal(text, email.from_email):
        if digest_like or generic_job_digest or _contains_any(text, NEWSLETTER_TERMS):
            category = "newsletter"
        elif _contains_any(text, MARKETING_TERMS):
            category = "promotion"

    deadline = _extract_datetime(text, DEADLINE_MARKERS)
    event_date = _extract_datetime(text, EVENT_MARKERS)
    company = _extract_company(email.from_email, email.subject, cleaned_body)
    reason = "Heuristic extraction used for a controlled test path."

    return ExtractedMetadata(
        category=category,
        reason=reason,
        action_required=action_required,
        deadline=deadline,
        event_date=event_date,
        company=company,
        summary=_default_summary(email.subject, cleaned_body),
        confidence=0.55 if not is_bulk else 0.7,
        is_bulk=is_bulk,
        action_channel=derive_action_channel(action_required=action_required, signals=signals),
        ai_source="heuristic",
        prompt_version=EMAIL_EXTRACTION_PROMPT_VERSION,
        processing_version=PROCESSING_VERSION,
    )


def _should_short_circuit_bulk_heuristic(
    *,
    email: EmailIngestItem,
    cleaned_body: str,
    heuristic: ExtractedMetadata,
) -> bool:
    if heuristic.category not in {"promotion", "newsletter"}:
        return False
    if not heuristic.is_bulk or heuristic.action_required or heuristic.action_channel != "none":
        return False

    text = f"{email.subject}\n{cleaned_body}".lower()
    if _strong_job_signal(text, email.from_email):
        return False
    if _contains_any(text, SCHOOL_CONTEXT_TERMS) or _contains_any(text, BILL_CONTEXT_TERMS):
        return False

    marketing_hits = _count_any(text, MARKETING_TERMS)
    newsletter_hits = _count_any(text, NEWSLETTER_TERMS)
    return bool(
        marketing_hits
        or newsletter_hits
        or _looks_like_content_digest(text, email.from_email)
        or _looks_like_generic_job_digest(text, email.from_email)
        or _is_bulk_sender(email.from_email)
    )


class LLMExtractionPayload(BaseModel):
    category: Category
    reason: str = ""
    action_required: bool = False
    deadline: str | None = None
    event_date: str | None = None
    company: str | None = None
    summary: str = ""
    confidence: float = 0.0
    is_bulk: bool = False
    action_channel: ActionChannel = "none"


def _parse_optional_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = date_parser.parse(value)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_llm_extraction_payload(
    data: dict[str, Any],
    *,
    email: EmailIngestItem,
    cleaned_body: str,
) -> ExtractedMetadata | None:
    try:
        parsed = LLMExtractionPayload.model_validate(data)
    except ValidationError:
        return None

    return ExtractedMetadata(
        category=parsed.category,
        reason=parsed.reason.strip() or "OpenAI extraction",
        action_required=parsed.action_required,
        deadline=_parse_optional_datetime(parsed.deadline),
        event_date=_parse_optional_datetime(parsed.event_date),
        company=parsed.company.strip() if isinstance(parsed.company, str) and parsed.company.strip() else None,
        summary=parsed.summary.strip() or _default_summary(email.subject, cleaned_body),
        confidence=max(0.0, min(1.0, float(parsed.confidence))),
        is_bulk=parsed.is_bulk,
        action_channel=parsed.action_channel,
        ai_source="openai",
        prompt_version=EMAIL_EXTRACTION_PROMPT_VERSION,
        processing_version=PROCESSING_VERSION,
    )


def _llm_extract(
    email: EmailIngestItem,
    cleaned_body: str,
    profile: UserProfile,
) -> ExtractedMetadata:
    try:
        client = get_openai_client()
        user_payload = build_extraction_user_payload(email, cleaned_body, profile)
        completion = run_openai_request(
            lambda: client.chat.completions.create(
                model=settings.openai_chat_model,
                temperature=settings.openai_chat_temperature,
                top_p=settings.openai_chat_top_p,
                frequency_penalty=settings.openai_chat_frequency_penalty,
                presence_penalty=settings.openai_chat_presence_penalty,
                max_completion_tokens=EXTRACTION_MAX_COMPLETION_TOKENS,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": EMAIL_EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(user_payload)},
                ],
            )
        )
        raw = completion.choices[0].message.content or "{}"
        data: dict[str, Any] = json.loads(raw)
        parsed = parse_llm_extraction_payload(
            data,
            email=email,
            cleaned_body=cleaned_body,
        )
        if parsed is None:
            logger.warning(
                "OpenAI returned an invalid extraction payload for %s; using heuristic fallback. Raw=%s",
                email.external_id,
                raw[:1000],
            )
            heuristic = _heuristic_extract(email, cleaned_body)
            heuristic.reason = _append_reason(
                heuristic.reason,
                "LLM payload was invalid, so heuristic extraction was used.",
            )
            record_ai_success()
            return heuristic
        record_ai_success()
        return parsed
    except Exception as exc:
        raise_ai_processing_error("extraction", exc)


def extract_metadata(
    email: EmailIngestItem,
    cleaned_body: str,
    profile: UserProfile,
    *,
    allow_fallback: bool = False,
) -> ExtractedMetadata:
    heuristic = _heuristic_extract(email, cleaned_body)
    base = (
        heuristic
        if allow_fallback or _should_short_circuit_bulk_heuristic(
            email=email,
            cleaned_body=cleaned_body,
            heuristic=heuristic,
        )
        else _llm_extract(email, cleaned_body, profile)
    )
    constrained = _apply_profile_constraints(
        email=email,
        cleaned_body=cleaned_body,
        metadata=base,
        profile=profile,
    )
    return _apply_response_intent_signals(
        email=email,
        cleaned_body=cleaned_body,
        metadata=constrained,
    )
