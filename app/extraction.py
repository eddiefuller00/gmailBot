from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from dateutil import parser as date_parser
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.profile_preferences import (
    profile_deprioritize_categories,
    profile_priority_categories,
)
from app.prompting import EMAIL_EXTRACTION_SYSTEM_PROMPT, build_extraction_user_payload
from app.schemas import Category, EmailIngestItem, ExtractedMetadata, UserProfile

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - runtime optional
    OpenAI = None  # type: ignore[assignment]


CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "job": [
        "interview",
        "recruiter",
        "application",
        "offer",
        "internship",
        "hiring",
        "candidate",
        "assessment",
    ],
    "school": [
        "assignment",
        "course",
        "professor",
        "campus",
        "class",
        "syllabus",
        "exam",
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
    "season tickets",
]

NEWSLETTER_TERMS = [
    "newsletter",
    "digest",
    "roundup",
    "weekly update",
    "you are invited",
    "learn how to",
    "jobs picked for you",
    "recommended for you",
]

STRONG_JOB_TERMS = [
    "interview",
    "application status",
    "hiring manager",
    "recruiter",
    "talent team",
    "candidate",
    "assessment",
    "offer letter",
    "next steps",
    "confirm your interview",
]

GENERIC_JOB_MARKETING_TERMS = [
    "job market",
    "career tips",
    "land a job",
    "jobs picked for you",
    "recommended jobs",
]

BULK_SENDER_TERMS = [
    "noreply",
    "no-reply",
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
    r"(?:interview|meeting|event|webinar)\s*(?:on|at)?\s*([A-Za-z]{3,9}\s+\d{1,2}(?:,\s*\d{4})?(?:\s+\d{1,2}:\d{2}\s*(?:am|pm))?)",
    r"(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2})",
]


def _default_summary(subject: str, body: str) -> str:
    without_urls = re.sub(r"https?://\S+", "", body, flags=re.IGNORECASE)
    stripped = re.sub(r"\s+", " ", without_urls).strip()
    if not stripped:
        return subject
    head = stripped[:220]
    return f"{subject}: {head}" if subject else head


def _contains_any(text: str, terms: list[str]) -> bool:
    lower = text.lower()
    return any(term in lower for term in terms)


def _pick_category(text: str) -> str:
    lower = text.lower()
    scores: dict[str, int] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        scores[category] = sum(1 for keyword in keywords if keyword in lower)
    best = max(scores.items(), key=lambda kv: kv[1])
    return best[0] if best[1] > 0 else "other"


def _extract_datetime(text: str, markers: list[str]) -> datetime | None:
    for pattern in markers:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            candidate = match.group(1).strip()
            try:
                parsed = date_parser.parse(candidate, fuzzy=True)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            except Exception:
                continue
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
    return any(term in lower for term in BULK_SENDER_TERMS)


def _has_strong_job_signal(text: str, from_email: str) -> bool:
    if _contains_any(text, STRONG_JOB_TERMS):
        return True
    lower = from_email.lower()
    if "recruit" in lower or "talent" in lower:
        return not _is_bulk_sender(from_email)
    return False


def _choose_marketing_category(text: str, from_email: str) -> Category:
    if _contains_any(text, NEWSLETTER_TERMS) or "newsletter" in from_email.lower():
        return "newsletter"
    return "promotion"


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
    bulk_sender = _is_bulk_sender(email.from_email)
    marketing_like = _contains_any(text, MARKETING_TERMS) or bulk_sender
    newsletter_like = _contains_any(text, NEWSLETTER_TERMS)
    strong_job_signal = _has_strong_job_signal(text, email.from_email)
    generic_job_marketing = _contains_any(text, GENERIC_JOB_MARKETING_TERMS)

    if (
        adjusted.category == "job"
        and not strong_job_signal
        and (marketing_like or newsletter_like or generic_job_marketing)
    ):
        adjusted.category = _choose_marketing_category(text, email.from_email)
        adjusted.action_required = False
        adjusted.deadline = None
        adjusted.event_date = None
        adjusted.reason = (
            f"{adjusted.reason}; reclassified as {adjusted.category} due to marketing/newsletter signals"
        ).strip("; ")

    if adjusted.category in {"promotion", "newsletter"}:
        adjusted.action_required = False
        if adjusted.category in deprioritized_categories:
            adjusted.deadline = None
            adjusted.event_date = None

    if (
        adjusted.category not in priority_categories
        and adjusted.category in deprioritized_categories
        and (marketing_like or newsletter_like)
    ):
        adjusted.reason = (
            f"{adjusted.reason}; deprioritized by onboarding preferences"
        ).strip("; ")

    return adjusted


def _heuristic_extract(email: EmailIngestItem, cleaned_body: str) -> ExtractedMetadata:
    text = f"{email.subject}\n{cleaned_body}"
    category = _pick_category(text)
    action_required = any(token in text.lower() for token in ACTION_KEYWORDS)
    deadline = _extract_datetime(text, DEADLINE_MARKERS)
    event_date = _extract_datetime(text, EVENT_MARKERS)
    company = _extract_company(email.from_email, email.subject, cleaned_body)

    reason_parts = []
    if category != "other":
        reason_parts.append(f"Matched {category} signals")
    if action_required:
        reason_parts.append("Contains action-oriented language")
    if deadline:
        reason_parts.append("Includes a deadline")
    if event_date:
        reason_parts.append("Includes an event date")
    reason = "; ".join(reason_parts) if reason_parts else "General informational email"

    return ExtractedMetadata(
        category=category,  # type: ignore[arg-type]
        reason=reason,
        action_required=action_required,
        deadline=deadline,
        event_date=event_date,
        company=company,
        summary=_default_summary(email.subject, cleaned_body),
    )


class LLMExtractionPayload(BaseModel):
    category: Category
    reason: str = ""
    action_required: bool = False
    deadline: str | None = None
    event_date: str | None = None
    company: str | None = None
    summary: str = ""


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

    deadline = _parse_optional_datetime(parsed.deadline)
    event_date = _parse_optional_datetime(parsed.event_date)
    summary = parsed.summary.strip() or _default_summary(email.subject, cleaned_body)
    reason = parsed.reason.strip() or "LLM extraction"
    company = parsed.company.strip() if isinstance(parsed.company, str) else None

    return ExtractedMetadata(
        category=parsed.category,
        reason=reason,
        action_required=parsed.action_required,
        deadline=deadline,
        event_date=event_date,
        company=company or None,
        summary=summary,
    )


def _llm_extract(
    email: EmailIngestItem, cleaned_body: str, profile: UserProfile
) -> ExtractedMetadata | None:
    if not settings.openai_api_key or OpenAI is None:
        return None

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        user_payload = build_extraction_user_payload(email, cleaned_body, profile)
        request_params: dict[str, Any] = {
            "model": settings.openai_chat_model,
            "temperature": settings.openai_chat_temperature,
            "top_p": settings.openai_chat_top_p,
            "frequency_penalty": settings.openai_chat_frequency_penalty,
            "presence_penalty": settings.openai_chat_presence_penalty,
            "max_tokens": settings.openai_chat_max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": EMAIL_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
        }
        if settings.openai_chat_seed is not None:
            request_params["seed"] = settings.openai_chat_seed
        if settings.openai_chat_stop_sequences:
            request_params["stop"] = list(settings.openai_chat_stop_sequences)

        completion = client.chat.completions.create(**request_params)
        raw = completion.choices[0].message.content or "{}"
        data: dict[str, Any] = json.loads(raw)
        parsed = parse_llm_extraction_payload(
            data,
            email=email,
            cleaned_body=cleaned_body,
        )
        if parsed is None:
            return None
        return parsed
    except Exception:
        return None


def extract_metadata(
    email: EmailIngestItem, cleaned_body: str, profile: UserProfile
) -> ExtractedMetadata:
    llm = _llm_extract(email, cleaned_body, profile)
    base = llm if llm is not None else _heuristic_extract(email, cleaned_body)
    return _apply_profile_constraints(
        email=email,
        cleaned_body=cleaned_body,
        metadata=base,
        profile=profile,
    )
