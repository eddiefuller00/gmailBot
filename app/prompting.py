from __future__ import annotations

from typing import Any

from app.profile_preferences import (
    expand_deprioritize_categories,
    expand_priority_categories,
    normalize_important_sender_preferences,
)
from app.schemas import EmailIngestItem, ProcessedEmail, UserProfile


EMAIL_EXTRACTION_PROMPT_VERSION = "email-extraction-v3"
ASK_INBOX_PROMPT_VERSION = "ask-inbox-v1"
PROCESSING_VERSION = "processing-v3"
MAX_EXTRACTION_BODY_CHARS = 1800
EXTRACTION_BODY_HEAD_CHARS = 1200
EXTRACTION_BODY_TAIL_CHARS = 500


EMAIL_EXTRACTION_SYSTEM_PROMPT = (
    "You are an inbox ranking analyst for a single user. "
    "Classify each email using the onboarding profile, extract the action channel, "
    "estimate confidence, and separate high-signal personal workflow from bulk automation. "
    "Base every decision on explicit evidence from the sender, subject, and body. "
    "Output strict JSON only."
)

EMAIL_EXTRACTION_RULES = [
    "Use the user's onboarding priorities as the primary ranking lens.",
    "Base every decision on sender, subject, and body evidence.",
    "Only classify as `job` or `school` when the email has direct candidacy or academic context.",
    "Treat promotions, newsletters, digests, and mass alerts as low-personal-relevance even if they sound urgent.",
    "Do not turn sale expirations or marketing deadlines into high-priority workflow items.",
    "Set `action_required=true` only when the email asks the user to do something concrete.",
    "Use `reply`, `portal`, `read`, or `none` for `action_channel`, and be conservative when uncertain.",
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
        "confidence",
        "is_bulk",
        "action_channel",
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
        "confidence": {"type": "number"},
        "is_bulk": {"type": "boolean"},
        "action_channel": {
            "type": "string",
            "enum": ["reply", "portal", "read", "none"],
        },
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
            "reason": "Recruiter follow-up that directly affects the user's interview process.",
            "action_required": True,
            "deadline": "2026-04-20T17:00:00Z",
            "event_date": None,
            "company": "Company",
            "summary": "Recruiter asks the user to confirm an interview time by April 20 at 5 PM.",
            "confidence": 0.98,
            "is_bulk": False,
            "action_channel": "reply",
        },
    },
    {
        "input": {
            "subject": "Registrar reminder: tuition payment due Friday",
            "from_email": "billing@university.edu",
            "body": "Your tuition balance is due Friday. Pay through the student portal.",
        },
        "output": {
            "category": "bill",
            "reason": "Direct school billing deadline tied to the user's academic account.",
            "action_required": True,
            "deadline": "2026-04-24T23:59:00Z",
            "event_date": None,
            "company": None,
            "summary": "University billing office says the tuition balance is due Friday in the portal.",
            "confidence": 0.95,
            "is_bulk": False,
            "action_channel": "portal",
        },
    },
    {
        "input": {
            "subject": "Professor Lee: draft feedback and office hours",
            "from_email": "lee@college.edu",
            "body": "I reviewed your draft. Please stop by office hours tomorrow if you want to discuss revisions.",
        },
        "output": {
            "category": "school",
            "reason": "Direct professor outreach connected to the user's coursework.",
            "action_required": True,
            "deadline": None,
            "event_date": "2026-04-22T15:00:00Z",
            "company": None,
            "summary": "Professor Lee reviewed the draft and invites the student to office hours tomorrow.",
            "confidence": 0.93,
            "is_bulk": False,
            "action_channel": "read",
        },
    },
    {
        "input": {
            "subject": "Dad: dinner on Sunday?",
            "from_email": "dad@gmail.com",
            "body": "Are you free for dinner Sunday night? Let me know.",
        },
        "output": {
            "category": "personal",
            "reason": "Personal message from a close contact that likely needs a reply.",
            "action_required": True,
            "deadline": None,
            "event_date": "2026-04-26T19:00:00Z",
            "company": None,
            "summary": "Dad asks whether the user is free for dinner on Sunday night.",
            "confidence": 0.94,
            "is_bulk": False,
            "action_channel": "reply",
        },
    },
    {
        "input": {
            "subject": "The latest jobs picked for you!",
            "from_email": "emails@emails.efinancialcareers.com",
            "body": "View all jobs. You received this email because you have an account. Unsubscribe and manage your preferences.",
        },
        "output": {
            "category": "newsletter",
            "reason": "Automated job digest for a broad audience rather than a direct candidacy update.",
            "action_required": False,
            "deadline": None,
            "event_date": None,
            "company": "Efinancialcareers",
            "summary": "Automated jobs digest with broad recommendations and preference links.",
            "confidence": 0.97,
            "is_bulk": True,
            "action_channel": "none",
        },
    },
    {
        "input": {
            "subject": "Treat yourself with 30% convenience order!",
            "from_email": "uber@uber.com",
            "body": "30% off convenience items until tonight. Terms apply. Unsubscribe.",
        },
        "output": {
            "category": "promotion",
            "reason": "Retail-style discount promotion unrelated to the user's stated workflow priorities.",
            "action_required": False,
            "deadline": None,
            "event_date": None,
            "company": "Uber",
            "summary": "Uber promotional discount on convenience orders with same-day expiry language.",
            "confidence": 0.99,
            "is_bulk": True,
            "action_channel": "none",
        },
    },
]


ASK_INBOX_SYSTEM_PROMPT = (
    "You answer inbox questions using only the provided email evidence. "
    "Return strict JSON with an `answer` string and a `citations` array of email ids. "
    "Cite only ids that appear in the supplied context. "
    "Be concise, factual, and prioritize what the user should handle first."
)


def _build_profile_policy(profile: UserProfile) -> dict[str, Any]:
    return {
        "priority_categories": sorted(expand_priority_categories(profile.priorities)),
        "deprioritized_categories": sorted(expand_deprioritize_categories(profile.deprioritize)),
        "important_sender_preferences": sorted(
            normalize_important_sender_preferences(profile.important_senders)
        ),
        "highlight_deadlines": profile.highlight_deadlines,
        "graduating_soon": profile.graduating_soon,
    }


def _truncate_extraction_body(cleaned_body: str) -> str:
    normalized = " ".join(cleaned_body.split())
    if len(normalized) <= MAX_EXTRACTION_BODY_CHARS:
        return normalized

    head = normalized[:EXTRACTION_BODY_HEAD_CHARS].rstrip()
    tail = normalized[-EXTRACTION_BODY_TAIL_CHARS:].lstrip()
    return f"{head} ... {tail}"


def build_extraction_user_payload(
    email: EmailIngestItem,
    cleaned_body: str,
    profile: UserProfile,
) -> dict[str, Any]:
    return {
        "rules": EMAIL_EXTRACTION_RULES,
        "profile_policy": _build_profile_policy(profile),
        "email": {
            "from_email": email.from_email,
            "from_name": email.from_name,
            "subject": email.subject,
            "received_at": email.received_at.isoformat(),
            "body": _truncate_extraction_body(cleaned_body),
        },
        "examples": EMAIL_EXTRACTION_FEW_SHOTS,
    }


def build_qa_user_payload(
    *,
    query: str,
    profile: UserProfile,
    emails: list[ProcessedEmail],
) -> dict[str, Any]:
    return {
        "profile_policy": _build_profile_policy(profile),
        "query": query,
        "emails": [
            {
                "id": email.external_id,
                "subject": email.subject,
                "from_email": email.from_email,
                "received_at": email.received_at.isoformat(),
                "importance": email.metadata.importance,
                "action_required": email.metadata.action_required,
                "deadline": email.metadata.deadline.isoformat()
                if email.metadata.deadline
                else None,
                "event_date": email.metadata.event_date.isoformat()
                if email.metadata.event_date
                else None,
                "summary": email.metadata.summary,
            }
            for email in emails
        ],
    }
