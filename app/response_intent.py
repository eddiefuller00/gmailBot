from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas import ActionChannel


URL_PATTERN = re.compile(r"(?:https?://\S+|www\.\S+)", flags=re.IGNORECASE)

NO_REPLY_LOCAL_PART_PATTERNS = [
    r"\bnoreply\b",
    r"\bno[-_.]?reply\b",
    r"\bdo[-_.]?not[-_.]?reply\b",
    r"\bdonotreply\b",
    r"\bmailer[-_.]?daemon\b",
    r"\balerts?\b",
    r"\bnotifications?\b",
    r"\bupdates?\b",
    r"\bdigest\b",
    r"\bnewsletters?\b",
    r"\bemails?\b",
]

NO_REPLY_BODY_PATTERNS = [
    r"\bdo not reply\b",
    r"\bdon't reply\b",
    r"\bplease do not (?:reply|respond)\b",
    r"\bdo not respond\b",
    r"\bdo not reply to this (?:email|message)\b",
    r"\bdo not respond to this (?:email|message)\b",
    r"\bno reply needed\b",
    r"\bno response needed\b",
    r"\bthis mailbox is not monitored\b",
    r"\bunmonitored mailbox\b",
    r"\bunattended mailbox\b",
    r"\bcannot receive repl(?:y|ies)\b",
    r"\bthis is an automated (?:email|message)\b",
    r"\bautomated message\b",
]

REPLY_REQUEST_PATTERNS = [
    r"\bplease reply\b",
    r"\bplease respond\b",
    r"\breply by\b",
    r"\brespond by\b",
    r"\blet me know\b",
    r"\bget back to (?:me|us)\b",
    r"\bemail (?:me|us)\b",
    r"\breply to this email\b",
]

LINK_CTA_TERMS = [
    "click",
    "view",
    "open",
    "review",
    "track",
    "verify",
    "reset",
    "sign in",
    "continue",
    "start here",
    "view online",
    "view in browser",
    "view this message in browser",
    "view this email in your browser",
    "read in browser",
    "read online",
    "read more",
    "manage preferences",
]


@dataclass(frozen=True)
class ResponseIntentSignals:
    no_reply_sender: bool
    link_only_cta: bool
    explicit_reply_requested: bool

    @property
    def likely_needs_reply(self) -> bool:
        return self.explicit_reply_requested and not self.no_reply_sender


def _contains_pattern(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def is_no_reply_sender(from_email: str) -> bool:
    lower = from_email.lower().strip()
    if "@" not in lower:
        return _contains_pattern(lower, NO_REPLY_LOCAL_PART_PATTERNS)

    local_part = lower.split("@", 1)[0]
    normalized = re.sub(r"[^a-z0-9]", "", local_part)
    if normalized in {
        "noreply",
        "donotreply",
        "mailerdaemon",
        "alert",
        "alerts",
        "notification",
        "notifications",
        "update",
        "updates",
        "digest",
        "newsletter",
        "newsletters",
        "email",
        "emails",
    }:
        return True
    return _contains_pattern(local_part, NO_REPLY_LOCAL_PART_PATTERNS)


def detect_response_intent(
    *,
    from_email: str,
    subject: str,
    body: str,
) -> ResponseIntentSignals:
    text = f"{subject}\n{body}".strip()
    lower = text.lower()
    no_reply_hint_in_body = _contains_pattern(lower, NO_REPLY_BODY_PATTERNS)
    explicit_reply_requested = _contains_pattern(lower, REPLY_REQUEST_PATTERNS)
    no_reply_sender = is_no_reply_sender(from_email) or no_reply_hint_in_body

    urls = URL_PATTERN.findall(text)
    url_count = len(urls)
    text_without_urls = URL_PATTERN.sub(" ", lower)
    non_url_words = re.findall(r"[a-z0-9']+", text_without_urls)
    non_url_word_count = len(non_url_words)
    cta_hits = sum(1 for term in LINK_CTA_TERMS if term in lower)

    link_only_cta = False
    if url_count > 0 and not explicit_reply_requested:
        if cta_hits >= 2 and non_url_word_count <= 90:
            link_only_cta = True
        elif url_count >= 2 and non_url_word_count <= 55:
            link_only_cta = True
        elif url_count >= 1 and non_url_word_count <= 40:
            link_only_cta = True
        elif no_reply_hint_in_body and cta_hits >= 1:
            link_only_cta = True

    if no_reply_sender and explicit_reply_requested:
        explicit_reply_requested = False

    return ResponseIntentSignals(
        no_reply_sender=no_reply_sender,
        link_only_cta=link_only_cta,
        explicit_reply_requested=explicit_reply_requested,
    )


def derive_action_channel(
    *,
    action_required: bool,
    signals: ResponseIntentSignals,
) -> ActionChannel:
    if signals.likely_needs_reply:
        return "reply"
    if action_required and (signals.link_only_cta or signals.no_reply_sender):
        return "portal"
    if action_required or signals.link_only_cta:
        return "read"
    return "none"
