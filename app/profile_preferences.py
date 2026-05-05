from __future__ import annotations

import hashlib
import json
import re

from app.schemas import UserProfile


_PRIORITY_KEYWORD_MAP: dict[str, set[str]] = {
    "job": {"job"},
    "jobs": {"job"},
    "career": {"job"},
    "careers": {"job"},
    "employment": {"job"},
    "internship": {"job"},
    "internships": {"job"},
    "recruiter": {"job"},
    "recruiters": {"job"},
    "recruiting": {"job"},
    "hiring": {"job"},
    "application": {"job"},
    "applications": {"job"},
    "school": {"school"},
    "schools": {"school"},
    "academic": {"school"},
    "academics": {"school"},
    "class": {"school"},
    "classes": {"school"},
    "course": {"school"},
    "courses": {"school"},
    "college": {"school"},
    "university": {"school"},
    "campus": {"school"},
    "professor": {"school"},
    "professors": {"school"},
    "exam": {"school"},
    "exams": {"school"},
    "assignment": {"school"},
    "assignments": {"school"},
    "homework": {"school"},
    "bill": {"bill"},
    "bills": {"bill"},
    "billing": {"bill"},
    "invoice": {"bill"},
    "invoices": {"bill"},
    "payment": {"bill"},
    "payments": {"bill"},
    "subscription": {"bill"},
    "subscriptions": {"bill"},
    "renewal": {"bill"},
    "renewals": {"bill"},
    "tuition": {"bill"},
    "event": {"event"},
    "events": {"event"},
    "calendar": {"event"},
    "meeting": {"event"},
    "meetings": {"event"},
    "invite": {"event"},
    "invites": {"event"},
    "webinar": {"event"},
    "webinars": {"event"},
    "workshop": {"event"},
    "workshops": {"event"},
    "conference": {"event"},
    "conferences": {"event"},
}

_DEPRIORITIZE_KEYWORD_MAP: dict[str, set[str]] = {
    "promotion": {"promotion"},
    "promotions": {"promotion"},
    "marketing": {"promotion"},
    "advertising": {"promotion"},
    "ads": {"promotion"},
    "ad": {"promotion"},
    "deals": {"promotion"},
    "deal": {"promotion"},
    "coupon": {"promotion"},
    "coupons": {"promotion"},
    "discount": {"promotion"},
    "discounts": {"promotion"},
    "sale": {"promotion"},
    "sales": {"promotion"},
    "offer": {"promotion"},
    "offers": {"promotion"},
    "newsletter": {"newsletter"},
    "newsletters": {"newsletter"},
    "digest": {"newsletter"},
    "digests": {"newsletter"},
    "roundup": {"newsletter"},
    "roundups": {"newsletter"},
    "bulletin": {"newsletter"},
    "bulletins": {"newsletter"},
    "updates": {"newsletter"},
    "update": {"newsletter"},
}

_IMPORTANT_SENDER_ALIAS_MAP: dict[str, str] = {
    "recruiter": "recruiters",
    "recruiters": "recruiters",
    "recruiting": "recruiters",
    "talent": "recruiters",
    "hiring": "recruiters",
    "hr": "recruiters",
    "professor": "professors",
    "professors": "professors",
    "faculty": "professors",
    "instructor": "professors",
    "teachers": "professors",
    "teacher": "professors",
    "company": "companies",
    "companies": "companies",
    "employer": "companies",
    "employers": "companies",
    "startup": "companies",
    "startups": "companies",
    "business": "companies",
    "businesses": "companies",
}

_WORD_PATTERN = re.compile(r"[a-z0-9]+")
PROFILE_PROCESSING_VERSION = "profile-processing-v2"


def _tokenize(value: str) -> list[str]:
    return _WORD_PATTERN.findall(value.lower())


def _candidate_keys(value: str) -> set[str]:
    tokens = _tokenize(value)
    candidates: set[str] = set(tokens)
    if not tokens:
        return candidates

    joined = " ".join(tokens)
    candidates.add(joined)

    for token in list(tokens):
        if token.endswith("s") and len(token) > 3:
            candidates.add(token[:-1])

    if len(tokens) >= 2:
        for i in range(len(tokens) - 1):
            candidates.add(f"{tokens[i]} {tokens[i + 1]}")
    return candidates


def _expand_categories(values: list[str], keyword_map: dict[str, set[str]]) -> set[str]:
    expanded: set[str] = set()
    for value in values:
        value_matches: set[str] = set()
        candidates = _candidate_keys(value)
        for candidate in candidates:
            mapped = keyword_map.get(candidate)
            if mapped:
                value_matches.update(mapped)
        if value_matches:
            expanded.update(value_matches)
            continue

        # Fallback pattern detection for unusual phrasing.
        joined = " ".join(_tokenize(value))
        if any(term in joined for term in ("job", "career", "intern", "recruit", "hiring")):
            expanded.add("job")
        if any(
            term in joined
            for term in ("school", "class", "course", "professor", "academic", "exam")
        ):
            expanded.add("school")
        if any(
            term in joined
            for term in ("bill", "billing", "invoice", "payment", "subscription", "renewal")
        ):
            expanded.add("bill")
        if any(
            term in joined
            for term in ("event", "meeting", "calendar", "webinar", "workshop", "invite")
        ):
            expanded.add("event")
        if any(
            term in joined
            for term in ("promo", "promotion", "sale", "deal", "discount", "coupon", "ad")
        ):
            expanded.add("promotion")
        if any(
            term in joined
            for term in ("newsletter", "digest", "roundup", "bulletin", "update")
        ):
            expanded.add("newsletter")
    return expanded


def expand_priority_categories(values: list[str]) -> set[str]:
    return _expand_categories(values, _PRIORITY_KEYWORD_MAP) & {
        "job",
        "school",
        "bill",
        "event",
    }


def expand_deprioritize_categories(values: list[str]) -> set[str]:
    return _expand_categories(values, _DEPRIORITIZE_KEYWORD_MAP) & {
        "promotion",
        "newsletter",
    }


def profile_priority_categories(profile: UserProfile) -> set[str]:
    return expand_priority_categories(profile.priorities)


def profile_deprioritize_categories(profile: UserProfile) -> set[str]:
    return expand_deprioritize_categories(profile.deprioritize)


def normalize_important_sender_preferences(values: list[str]) -> set[str]:
    normalized: set[str] = set()
    for raw in values:
        lowered = " ".join(raw.lower().split()).strip()
        if not lowered:
            continue

        tokens = _candidate_keys(lowered)
        canonical = None
        for token in tokens:
            canonical = _IMPORTANT_SENDER_ALIAS_MAP.get(token)
            if canonical:
                break
        normalized.add(canonical or lowered)
    return normalized


def profile_processing_fingerprint(profile: UserProfile) -> str:
    normalized = {
        "version": PROFILE_PROCESSING_VERSION,
        "role": sorted({" ".join(value.lower().split()) for value in profile.role if value.strip()}),
        "graduating_soon": bool(profile.graduating_soon),
        "priorities": sorted(expand_priority_categories(profile.priorities)),
        "important_senders": sorted(normalize_important_sender_preferences(profile.important_senders)),
        "deprioritize": sorted(expand_deprioritize_categories(profile.deprioritize)),
        "highlight_deadlines": bool(profile.highlight_deadlines),
    }
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
