from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from app.profile_preferences import (
    normalize_important_sender_preferences,
    profile_deprioritize_categories,
    profile_priority_categories,
)
from app.schemas import AlertItem, ProcessedEmail, UserProfile


NOISY_ALERT_CATEGORIES = {"promotion", "newsletter"}
NOISY_SUBJECT_TERMS = (
    "sale",
    "discount",
    "ticket",
    "season",
    "year in review",
    "vote",
    "voting",
    "promo",
    "coupon",
    "unsubscribe",
)


def _matches_important_sender(email: ProcessedEmail, profile: UserProfile) -> bool:
    preferences = normalize_important_sender_preferences(profile.important_senders)
    if not preferences:
        return False

    from_email = email.from_email.lower()
    if "recruiters" in preferences and any(
        token in from_email for token in ("recruit", "talent", "jobs", "careers")
    ):
        return True
    if "professors" in preferences and ".edu" in from_email:
        return True
    if "companies" in preferences and not any(
        token in from_email for token in ("noreply", "no-reply", "newsletter", "promo")
    ):
        return True

    for value in preferences:
        if value in {"recruiters", "professors", "companies"}:
            continue
        if value and value in from_email:
            return True
    return False


def _looks_noisy_marketing(email: ProcessedEmail) -> bool:
    text = f"{email.subject} {email.metadata.summary}".lower()
    return any(term in text for term in NOISY_SUBJECT_TERMS)


def _is_priority_email(
    email: ProcessedEmail,
    profile: UserProfile,
    *,
    priority_categories: set[str],
    deprioritize_categories: set[str],
) -> bool:
    category = email.metadata.category

    if category in deprioritize_categories:
        return False
    if category in NOISY_ALERT_CATEGORIES and category not in priority_categories:
        return False
    if category == "job" and email.metadata.is_bulk and not _matches_important_sender(email, profile):
        return False
    if _looks_noisy_marketing(email) and category not in priority_categories and category != "job":
        return False

    if category in priority_categories:
        return not email.metadata.is_bulk or _matches_important_sender(email, profile)
    if _matches_important_sender(email, profile):
        return True
    if email.metadata.importance >= 8.8 and email.metadata.action_required:
        return True
    return False


def _format_deadline_message(deadline: datetime, now: datetime, subject: str) -> str:
    delta = deadline - now
    if delta <= timedelta(0):
        return f"Deadline today: {subject}"
    if delta <= timedelta(hours=24):
        return f"Deadline within 24 hours: {subject}"
    days_left = max(1, int(math.ceil(delta.total_seconds() / 86400)))
    return f"Deadline in {days_left} day(s): {subject}"


def generate_alerts(
    *,
    profile: UserProfile,
    deadlines: list[ProcessedEmail],
    action_required: list[ProcessedEmail],
    top_important: list[ProcessedEmail],
    unread_important_count: int,
) -> list[AlertItem]:
    alerts: list[AlertItem] = []
    seen_messages: set[str] = set()
    now = datetime.now(timezone.utc)
    priority_categories = profile_priority_categories(profile)
    deprioritize_categories = profile_deprioritize_categories(profile)

    if profile.highlight_deadlines:
        deadline_alerts = 0
        for email in deadlines:
            if deadline_alerts >= 3:
                break
            if not email.metadata.deadline:
                continue
            if not _is_priority_email(
                email,
                profile,
                priority_categories=priority_categories,
                deprioritize_categories=deprioritize_categories,
            ):
                continue
            if email.metadata.importance < 7.0 and email.metadata.category not in priority_categories:
                continue

            deadline = email.metadata.deadline
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            delta = deadline - now
            if not (timedelta(0) <= delta <= timedelta(days=2)):
                continue

            message = _format_deadline_message(deadline, now, email.subject)
            if message in seen_messages:
                continue
            seen_messages.add(message)
            deadline_alerts += 1
            alerts.append(
                AlertItem(
                    message=message,
                    severity="high" if delta <= timedelta(hours=24) else "warning",
                )
            )

    job_alerts = 0
    for email in top_important:
        if job_alerts >= 3:
            break
        if not email.unread:
            continue
        if email.metadata.category != "job":
            continue
        if email.metadata.importance < 7.0:
            continue
        if not _is_priority_email(
            email,
            profile,
            priority_categories=priority_categories,
            deprioritize_categories=deprioritize_categories,
        ):
            continue

        message = (
            f"Job action needed: {email.subject}"
            if email.metadata.action_required
            else f"Important job update: {email.subject}"
        )
        if message in seen_messages:
            continue
        seen_messages.add(message)
        job_alerts += 1
        alerts.append(
            AlertItem(
                message=message,
                severity="high" if email.metadata.action_required else "warning",
            )
        )

    recruiter_stale = [
        email
        for email in action_required
        if email.unread
        and email.metadata.importance >= 7.0
        and any(term in email.from_email.lower() for term in ["recruit", "talent", "hiring"])
        and _is_priority_email(
            email,
            profile,
            priority_categories=priority_categories,
            deprioritize_categories=deprioritize_categories,
        )
        and email.metadata.action_channel == "reply"
        and (now - email.received_at.replace(tzinfo=email.received_at.tzinfo or timezone.utc))
        >= timedelta(days=5)
    ]
    for email in recruiter_stale[:2]:
        message = f"No response to recruiter email for 5+ days: {email.subject}"
        if message in seen_messages:
            continue
        seen_messages.add(message)
        alerts.append(
            AlertItem(
                message=message,
                severity="warning",
            )
        )

    priority_unread = {
        email.external_id
        for email in top_important
        if email.unread
        and email.metadata.importance >= 7.0
        and _is_priority_email(
            email,
            profile,
            priority_categories=priority_categories,
            deprioritize_categories=deprioritize_categories,
        )
    }

    if priority_unread:
        message = f"You have {len(priority_unread)} unread priority emails."
        if message not in seen_messages:
            seen_messages.add(message)
            alerts.append(
                AlertItem(
                    message=message,
                    severity="high" if len(priority_unread) >= 5 else "warning",
                )
            )
    elif unread_important_count >= 3:
        message = f"You have {unread_important_count} important unread emails."
        if message not in seen_messages:
            seen_messages.add(message)
            alerts.append(
                AlertItem(
                    message=message,
                    severity="warning",
                )
            )

    alerts = alerts[:6]

    if not alerts:
        alerts.append(
            AlertItem(
                message="No urgent alerts right now.",
                severity="info",
            )
        )
    return alerts
