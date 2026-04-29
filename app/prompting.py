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
MAX_EXTRACTION_BODY_CHARS = 4000
EXTRACTION_BODY_HEAD_CHARS = 2800
EXTRACTION_BODY_TAIL_CHARS = 1000


EMAIL_EXTRACTION_SYSTEM_PROMPT = (
    "You are an inbox ranking analyst for a single user. "
    "Classify each email using the onboarding profile, extract the action channel, "
    "estimate confidence, and separate high-signal personal workflow from bulk automation. "
    "Base every decision on explicit evidence from the sender, subject, and body. "
    "Output strict JSON only."
)

EMAIL_EXTRACTION_RULES = [
    "Prioritize what matters to this specific user over generic email taxonomy.",
    "Use the user's onboarding priorities as the primary ranking lens before generic urgency or recency.",
    "Use the user's priorities and important sender preferences to explain why the email matters.",
    "Base the category, action_required flag, and reason on concrete sender, subject, and body evidence, not on generic marketing phrasing alone.",
    "Only classify as 'job' when the email is directly about the user's candidacy, application, interview, assessment, offer, recruiter follow-up, or employer workflow.",
    "Only classify as 'school' when there is explicit academic context such as a professor, registrar, class, tuition, assignment, or campus workflow.",
    "Do not treat article headlines, shopping offers, mass recommendations, or entertainment/news digests as user priorities unless the onboarding profile explicitly prioritizes them.",
    "Classify bulk promotions, newsletters, digests, and content roundups as low-personal-relevance even if they contain urgency language.",
    "Do not elevate sale end dates, coupon expirations, or promotional deadlines into high-priority workflow items.",
    "Set `is_bulk=true` for automated campaigns, digests, no-reply senders, or broad-audience alerts.",
    "Use `action_channel=reply` only when the sender is asking for a direct response.",
    "Use `action_channel=portal` when the user needs to act through a link, site, or form rather than reply by email.",
    "Use `action_channel=read` for informational items the user should read soon but does not need to answer immediately.",
    "Use `action_channel=none` when no immediate user action is needed.",
    "Set `action_required=true` only when the email asks the user to do something concrete.",
    "Provide a concise `reason` that states why this email matters to the user.",
    "Return `confidence` as a number between 0 and 1.",
    "If uncertain, choose the conservative category and lower confidence.",
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
            "subject": "Team offsite agenda for Thursday",
            "from_email": "manager@startup.com",
            "body": "Here is the agenda for Thursday's offsite. Read before the meeting.",
        },
        "output": {
            "category": "event",
            "reason": "Work event coordination that the user should review before attending.",
            "action_required": True,
            "deadline": None,
            "event_date": "2026-04-23T09:00:00Z",
            "company": "Startup",
            "summary": "Manager sent the offsite agenda for Thursday and wants it reviewed in advance.",
            "confidence": 0.9,
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
            "subject": "Application update available",
            "from_email": "no-reply@jobs.example.com",
            "body": "Log in to your candidate portal to review the next step for your application.",
        },
        "output": {
            "category": "job",
            "reason": "Direct candidate workflow update that matters to the user's application progress.",
            "action_required": True,
            "deadline": None,
            "event_date": None,
            "company": "Jobs",
            "summary": "Candidate portal has a new application update and next step for the user.",
            "confidence": 0.91,
            "is_bulk": False,
            "action_channel": "portal",
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
            "subject": "Every TV show getting cancelled in 2026 (full list)",
            "from_email": "news@email.microsoftstart.com",
            "body": "Best of MSN roundup. Read online and manage your preferences.",
        },
        "output": {
            "category": "newsletter",
            "reason": "Content digest from a news sender, not a direct workflow item in the user's onboarding priorities.",
            "action_required": False,
            "deadline": None,
            "event_date": None,
            "company": "Microsoftstart",
            "summary": "MSN content roundup about canceled TV shows with read-online and preference links.",
            "confidence": 0.99,
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
    {
        "input": {
            "subject": "50% off tickets tonight",
            "from_email": "promo@tickets.com",
            "body": "Final sale ends tonight. Unsubscribe in footer.",
        },
        "output": {
            "category": "promotion",
            "reason": "Bulk marketing promotion unrelated to the user's stated priorities.",
            "action_required": False,
            "deadline": None,
            "event_date": None,
            "company": "Tickets",
            "summary": "Promotional ticket sale with same-day urgency.",
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
        "task": "Classify and extract actionable metadata for this email.",
        "prompt_version": EMAIL_EXTRACTION_PROMPT_VERSION,
        "processing_version": PROCESSING_VERSION,
        "rules": EMAIL_EXTRACTION_RULES,
        "profile": profile.model_dump(),
        "profile_policy": _build_profile_policy(profile),
        "email": {
            "from_email": email.from_email,
            "from_name": email.from_name,
            "subject": email.subject,
            "received_at": email.received_at.isoformat(),
            "body": _truncate_extraction_body(cleaned_body),
        },
        "examples": EMAIL_EXTRACTION_FEW_SHOTS,
        "output_schema": EMAIL_EXTRACTION_OUTPUT_SCHEMA,
    }


def build_qa_user_payload(
    *,
    query: str,
    profile: UserProfile,
    emails: list[ProcessedEmail],
) -> dict[str, Any]:
    return {
        "task": "Answer the inbox question using the supplied emails and cite the ids you used.",
        "prompt_version": ASK_INBOX_PROMPT_VERSION,
        "profile": profile.model_dump(),
        "profile_policy": _build_profile_policy(profile),
        "query": query,
        "emails": [
            {
                "id": email.external_id,
                "subject": email.subject,
                "from_email": email.from_email,
                "received_at": email.received_at.isoformat(),
                "importance": email.metadata.importance,
                "category": email.metadata.category,
                "action_required": email.metadata.action_required,
                "action_channel": email.metadata.action_channel,
                "deadline": email.metadata.deadline.isoformat()
                if email.metadata.deadline
                else None,
                "event_date": email.metadata.event_date.isoformat()
                if email.metadata.event_date
                else None,
                "reason": email.metadata.reason,
                "summary": email.metadata.summary,
            }
            for email in emails
        ],
        "output_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["answer", "citations"],
            "properties": {
                "answer": {"type": "string"},
                "citations": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
    }
