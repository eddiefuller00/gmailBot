from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import db
from app.extraction import extract_metadata
from app.gmail_integration import get_gmail_message_detail, list_gmail_message_ids
from app.preprocess import clean_email_body
from app.qa import answer_query
from app.retrieval import embed_text, semantic_rank
from app.scoring import compute_importance
from app.schemas import (
    DashboardResponse,
    EmailIngestItem,
    GmailMessageDetail,
    ProcessedEmail,
    QAResponse,
    UserProfile,
)


def _dedupe_by_external_id(items: list[ProcessedEmail]) -> list[ProcessedEmail]:
    seen: set[str] = set()
    unique: list[ProcessedEmail] = []
    for item in items:
        if item.external_id in seen:
            continue
        seen.add(item.external_id)
        unique.append(item)
    return unique


def process_email(email: EmailIngestItem, profile: UserProfile) -> None:
    cleaned = clean_email_body(email.body)
    metadata = extract_metadata(email, cleaned, profile)
    score, breakdown = compute_importance(email, metadata, profile)
    metadata.importance = score
    metadata.scoring_breakdown = breakdown
    if not metadata.summary:
        metadata.summary = cleaned[:220]
    embedding = embed_text(f"{email.subject}\n{cleaned}\n{metadata.summary}")
    db.upsert_processed_email(
        external_id=email.external_id,
        from_email=email.from_email,
        from_name=email.from_name,
        subject=email.subject,
        body=email.body,
        cleaned_body=cleaned,
        received_at=email.received_at,
        unread=email.unread,
        metadata=metadata,
        embedding=embedding,
    )


def build_dashboard(top_n: int = 5) -> DashboardResponse:
    top_important = _dedupe_by_external_id(db.list_top_important(limit=top_n))
    upcoming_deadlines = []
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=14)
    for email in db.list_with_deadlines(limit=30):
        if email.metadata.deadline is None:
            continue
        deadline = email.metadata.deadline
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if now <= deadline <= horizon:
            upcoming_deadlines.append(email)
    upcoming_events = []
    for email in db.list_with_events(limit=30):
        if email.metadata.event_date is None:
            continue
        event_date = email.metadata.event_date
        if event_date.tzinfo is None:
            event_date = event_date.replace(tzinfo=timezone.utc)
        if now <= event_date <= horizon:
            upcoming_events.append(email)

    job_updates = _dedupe_by_external_id(db.list_by_category("job", limit=20))[:10]

    excluded_ids = {email.external_id for email in top_important}
    excluded_ids.update(email.external_id for email in job_updates)
    action_required = [
        email
        for email in _dedupe_by_external_id(db.list_action_required(limit=40))
        if email.external_id not in excluded_ids
    ][:10]

    return DashboardResponse(
        top_important_emails=top_important,
        upcoming_deadlines=upcoming_deadlines[:10],
        upcoming_events=upcoming_events[:10],
        job_updates=job_updates,
        action_required=action_required,
    )


def qa_over_inbox(query: str, limit: int = 8) -> QAResponse:
    vectors = db.get_email_vectors(limit=2000)
    ranked = semantic_rank(query, vectors, limit=max(limit, 12))
    answer, supporting = answer_query(query, ranked)
    return QAResponse(answer=answer, supporting_emails=supporting[:limit])


def list_recent_emails(limit: int = 50) -> list[ProcessedEmail]:
    return db.list_processed_emails(limit=limit)


def _gmail_detail_to_ingest_item(detail: GmailMessageDetail) -> EmailIngestItem:
    received_at = detail.received_at or datetime.now(timezone.utc)
    body = (detail.body_text or detail.snippet or "").strip()
    if not body:
        body = detail.subject or "(No content)"

    return EmailIngestItem(
        external_id=f"gmail:{detail.id}",
        from_email=detail.from_email or "unknown@googlemail.local",
        from_name=detail.from_name,
        subject=detail.subject or "(No Subject)",
        body=body,
        received_at=received_at,
        unread=detail.is_unread,
    )


def sync_connected_gmail(
    *,
    max_messages: int = 150,
    query: str | None = None,
    label_ids: list[str] | None = None,
    clear_non_gmail: bool = False,
) -> int:
    if clear_non_gmail:
        db.delete_non_gmail_emails()

    profile = db.get_profile()
    ingested = 0
    page_token: str | None = None
    seen_message_ids: set[str] = set()

    while ingested < max_messages:
        remaining = max_messages - ingested
        page_size = min(50, remaining)
        message_ids, next_page_token = list_gmail_message_ids(
            max_results=page_size,
            page_token=page_token,
            query=query,
            label_ids=label_ids or ["INBOX"],
        )
        if not message_ids:
            break

        for message_id in message_ids:
            if message_id in seen_message_ids:
                continue
            seen_message_ids.add(message_id)
            detail = get_gmail_message_detail(message_id)
            ingest_item = _gmail_detail_to_ingest_item(detail)
            process_email(ingest_item, profile)
            ingested += 1
            if ingested >= max_messages:
                break

        if not next_page_token:
            break
        page_token = next_page_token

    return ingested
