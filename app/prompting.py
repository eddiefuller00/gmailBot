from __future__ import annotations

from typing import Any

from app.profile_preferences import (
    expand_deprioritize_categories,
    expand_priority_categories,
    normalize_important_sender_preferences,
)
from app.schemas import EmailIngestItem, UserProfile


EMAIL_EXTRACTION_SYSTEM_PROMPT = (
    "You are an inbox ranking analyst. "
    "Classify each email for personal relevance using the user's onboarding profile. "
    "Do not inflate urgency for bulk promotions/newsletters. "
    "Follow the required schema exactly and output strict JSON only."
)

EMAIL_EXTRACTION_RULES = [
    "Prioritize precision over recall. If uncertain, choose a conservative category.",
    "Treat onboarding profile preferences as hard constraints for relevance.",
    "Do not classify an email as 'job' unless it is directly about this user's candidacy, application, interview, assessment, offer, or recruiter follow-up.",
    "Classify bulk marketing, ticket sales, and generic career-advice blasts as 'promotion' or 'newsletter' even if they contain urgency words like 'last chance' or 'today'.",
    "Set action_required=true only when the sender asks the user to complete a concrete task (reply/submit/confirm/pay/register) tied to that user's goals.",
    "Do not set action_required=true for commercial calls-to-action like buy/shop/save/claim now.",
    "Only emit fields in the required schema.",
    "If a field is unknown, use null (or false for booleans).",
]

EMAIL_EXTRACTION_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "category",
        "reason",
        "action_required",
        "deadline",
        "event_date",
        "company",
        "summary",
    ],
    "properties": {
        "category": {
            "type": "string",
            "enum": [
                "job",
                "school",
                "bill",
                "event",
                "promotion",
                "newsletter",
                "personal",
                "other",
            ],
        },
        "reason": {"type": "string"},
        "action_required": {"type": "boolean"},
        "deadline": {"type": ["string", "null"]},
        "event_date": {"type": ["string", "null"]},
        "company": {"type": ["string", "null"]},
        "summary": {"type": "string"},
    },
}

EMAIL_EXTRACTION_FEW_SHOTS: list[dict[str, Any]] = [
    {
        "input": {
            "subject": "Interview scheduling request",
            "from_email": "talent@company.com",
            "body": "Please confirm your interview slot by April 20 at 5 PM.",
        },
        "output": {
            "category": "job",
            "reason": "Recruiting context with explicit response deadline",
            "action_required": True,
            "deadline": "2026-04-20T17:00:00Z",
            "event_date": None,
            "company": "Company",
            "summary": "Recruiter asks you to confirm an interview slot by April 20 at 5 PM.",
        },
    },
    {
        "input": {
            "subject": "50% off tickets tonight",
            "from_email": "promo@tickets.com",
            "body": "Final sale ends tonight. Unsubscribe in footer.",
        },
        "output": {
            "category": "promotion",
            "reason": "Marketing promotion language with sale urgency",
            "action_required": False,
            "deadline": None,
            "event_date": None,
            "company": "Tickets",
            "summary": "Promotional sale email with a same-day discount offer.",
        },
    },
    {
        "input": {
            "subject": "LAST CHANCE! Save 50% on Select Seats",
            "from_email": "yankees@marketing.mlbemail.com",
            "body": "Walk-Off Offer TODAY ONLY! View online and unsubscribe at the bottom.",
        },
        "output": {
            "category": "promotion",
            "reason": "Bulk ticket marketing with sales language and unsubscribe signals",
            "action_required": False,
            "deadline": None,
            "event_date": None,
            "company": "Yankees",
            "summary": "Ticket-sale promotion advertising a limited-time discount.",
        },
    },
    {
        "input": {
            "subject": "You are invited: Learn how to land a job in today's market",
            "from_email": "linkedin@em.linkedin.com",
            "body": "General career webinar invitation with unsubscribe links.",
        },
        "output": {
            "category": "newsletter",
            "reason": "General audience career content, not a specific candidacy update",
            "action_required": False,
            "deadline": None,
            "event_date": None,
            "company": "Linkedin",
            "summary": "Generic career-advice newsletter invitation.",
        },
    },
]


def _build_profile_policy(profile: UserProfile) -> dict[str, Any]:
    priority_categories = sorted(expand_priority_categories(profile.priorities))
    deprioritize_categories = sorted(expand_deprioritize_categories(profile.deprioritize))

    return {
        "priority_categories": priority_categories,
        "deprioritized_categories": deprioritize_categories,
        "important_sender_preferences": sorted(
            normalize_important_sender_preferences(profile.important_senders)
        ),
        "highlight_deadlines": profile.highlight_deadlines,
        "graduating_soon": profile.graduating_soon,
        "strict_notes": [
            "If an email matches deprioritized categories and is not explicitly user-critical, keep it out of high-priority classes.",
            "Only promote deadlines/events that align with priority categories or important senders.",
            "When in doubt between 'job' and marketing/newsletter, prefer marketing/newsletter unless there is candidacy-specific evidence.",
        ],
    }


def build_extraction_user_payload(
    email: EmailIngestItem,
    cleaned_body: str,
    profile: UserProfile,
) -> dict[str, Any]:
    return {
        "task": "Classify and extract actionable metadata for this email.",
        "rules": EMAIL_EXTRACTION_RULES,
        "profile": profile.model_dump(),
        "profile_policy": _build_profile_policy(profile),
        "email": {
            "from_email": email.from_email,
            "from_name": email.from_name,
            "subject": email.subject,
            "received_at": email.received_at.isoformat(),
            "body": cleaned_body,
        },
        "examples": EMAIL_EXTRACTION_FEW_SHOTS,
        "output_schema": EMAIL_EXTRACTION_OUTPUT_SCHEMA,
    }
