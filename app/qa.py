from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.schemas import ProcessedEmail


def _is_recruiter_email(email: ProcessedEmail) -> bool:
    lower = f"{email.from_email} {email.subject} {email.metadata.summary}".lower()
    return any(word in lower for word in ["recruit", "talent", "hiring", "career"])


def _format_email_line(email: ProcessedEmail) -> str:
    date = email.received_at.strftime("%Y-%m-%d")
    return f"[{date}] {email.subject} ({email.from_email}) - score {email.metadata.importance:.1f}"


def _deadline_in_next_days(email: ProcessedEmail, days: int) -> bool:
    if not email.metadata.deadline:
        return False
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)
    deadline = email.metadata.deadline
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return now <= deadline <= end


def answer_query(query: str, candidates: list[ProcessedEmail]) -> tuple[str, list[ProcessedEmail]]:
    q = query.lower().strip()

    if "interview" in q:
        selected = [
            email
            for email in candidates
            if email.metadata.category == "job" and email.metadata.event_date is not None
        ]
        if not selected:
            return "No interview events were found in the indexed emails.", []
        lines = "\n".join(_format_email_line(email) for email in selected[:6])
        return f"I found these interview-related emails:\n{lines}", selected[:6]

    if "deadline" in q and ("week" in q or "this week" in q):
        selected = [email for email in candidates if _deadline_in_next_days(email, 7)]
        if not selected:
            return "No deadlines were detected in the next 7 days.", []
        lines = "\n".join(_format_email_line(email) for email in selected[:6])
        return f"These deadlines are coming up this week:\n{lines}", selected[:6]

    if "recruiter" in q:
        selected = [email for email in candidates if _is_recruiter_email(email)]
        if not selected:
            return "No recruiter replies were identified in the current index.", []
        lines = "\n".join(_format_email_line(email) for email in selected[:6])
        return f"I found recruiter-related emails:\n{lines}", selected[:6]

    if "respond" in q or "first" in q:
        selected = [
            email for email in candidates if email.metadata.action_required or email.unread
        ]
        selected.sort(
            key=lambda email: (email.metadata.importance, email.received_at.timestamp()),
            reverse=True,
        )
        if not selected:
            return "No response-priority emails were identified.", []
        lines = "\n".join(_format_email_line(email) for email in selected[:6])
        return f"Reply to these first based on urgency and importance:\n{lines}", selected[:6]

    selected = sorted(
        candidates,
        key=lambda email: (email.metadata.importance, email.received_at.timestamp()),
        reverse=True,
    )[:6]
    if not selected:
        return "No emails are currently indexed. Ingest emails to ask inbox questions.", []
    lines = "\n".join(_format_email_line(email) for email in selected)
    return f"Top relevant emails for your query:\n{lines}", selected

