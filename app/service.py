from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock

from app import db
from app.ai_runtime import AIProcessingError, AIRuntimeError
from app.extraction import extract_metadata
from app.gmail_integration import get_gmail_message_detail, list_gmail_message_ids
from app.profile_preferences import (
    normalize_important_sender_preferences,
    profile_deprioritize_categories,
    profile_priority_categories,
    profile_processing_fingerprint,
)
from app.preprocess import clean_email_body
from app.prompting import EMAIL_EXTRACTION_PROMPT_VERSION, PROCESSING_VERSION
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


@dataclass(frozen=True)
class GmailSyncResult:
    ingested: int
    has_more: bool
    backfill_complete: bool | None


NOISY_DASHBOARD_CATEGORIES = {"promotion", "newsletter"}
NOISY_DASHBOARD_TERMS = (
    "sale",
    "discount",
    "coupon",
    "promo",
    "unsubscribe",
    "view online",
    "read online",
    "manage your preferences",
    "% off",
    "deal",
)
PROFILE_SCORE_REFRESH_LOCK = Lock()


def _dedupe_by_external_id(items: list[ProcessedEmail]) -> list[ProcessedEmail]:
    seen: set[str] = set()
    unique: list[ProcessedEmail] = []
    for item in items:
        if item.external_id in seen:
            continue
        seen.add(item.external_id)
        unique.append(item)
    return unique


def _gmail_connected() -> bool:
    return db.get_google_oauth_token() is not None


def _exclude_legacy_sample_rows(items: list[ProcessedEmail]) -> list[ProcessedEmail]:
    if not _gmail_connected():
        return items
    return [item for item in items if not item.external_id.startswith("smoke-")]


def build_content_fingerprint(email: EmailIngestItem, cleaned_body: str) -> str:
    normalized = json.dumps(
        {
            "from_email": email.from_email.lower().strip(),
            "subject": email.subject.strip(),
            "cleaned_body": cleaned_body.strip(),
            "received_at": email.received_at.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def process_email(
    email: EmailIngestItem,
    profile: UserProfile,
    *,
    gmail_message_id: str | None = None,
    gmail_thread_id: str | None = None,
    cleaned_body: str | None = None,
    content_fingerprint: str | None = None,
) -> None:
    cleaned = cleaned_body or clean_email_body(email.body)
    fingerprint = content_fingerprint or build_content_fingerprint(email, cleaned)
    metadata = extract_metadata(email, cleaned, profile)
    score, breakdown = compute_importance(email, metadata, profile)
    metadata.importance = score
    metadata.profile_fingerprint = profile_processing_fingerprint(profile)
    metadata.scoring_breakdown = breakdown
    if not metadata.summary:
        metadata.summary = cleaned[:220]
    embedding = embed_text(f"{email.subject}\n{cleaned}\n{metadata.summary}")
    now = datetime.now(timezone.utc)
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
        gmail_message_id=gmail_message_id,
        gmail_thread_id=gmail_thread_id,
        content_fingerprint=fingerprint,
        last_processed_at=now,
        last_synced_at=now,
    )


def ensure_processing_versions_current(profile: UserProfile, limit: int = 200) -> None:
    if limit <= 0:
        return

    outdated = db.list_outdated_processed_emails(
        prompt_version=EMAIL_EXTRACTION_PROMPT_VERSION,
        processing_version=PROCESSING_VERSION,
        limit=limit,
    )
    for email in outdated:
        try:
            process_email(
                EmailIngestItem(
                    external_id=email.external_id,
                    from_email=email.from_email,
                    from_name=email.from_name,
                    subject=email.subject,
                    body=email.body,
                    received_at=email.received_at,
                    unread=email.unread,
                ),
                profile,
                gmail_message_id=email.gmail_message_id,
                gmail_thread_id=email.gmail_thread_id,
                cleaned_body=email.cleaned_body,
                content_fingerprint=build_content_fingerprint(
                    EmailIngestItem(
                        external_id=email.external_id,
                        from_email=email.from_email,
                        from_name=email.from_name,
                        subject=email.subject,
                        body=email.body,
                        received_at=email.received_at,
                        unread=email.unread,
                    ),
                    email.cleaned_body,
                ),
            )
        except (AIRuntimeError, AIProcessingError):
            # Version refresh is best-effort; keep serving stored rows on transient AI failures.
            break


def refresh_profile_scores(profile: UserProfile, limit: int = 200) -> int:
    if limit <= 0:
        return 0
    if not PROFILE_SCORE_REFRESH_LOCK.acquire(blocking=False):
        return 0

    try:
        profile_fingerprint = profile_processing_fingerprint(profile)
        stale = db.list_profile_stale_processed_emails(
            profile_fingerprint=profile_fingerprint,
            limit=limit,
        )
        refreshed = 0
        for stored in stale:
            score, breakdown = compute_importance(
                EmailIngestItem(
                    external_id=stored.external_id,
                    from_email=stored.from_email,
                    from_name=stored.from_name,
                    subject=stored.subject,
                    body=stored.body,
                    received_at=stored.received_at,
                    unread=stored.unread,
                ),
                stored.metadata,
                profile,
            )
            stored.metadata.importance = score
            stored.metadata.scoring_breakdown = breakdown
            stored.metadata.profile_fingerprint = profile_fingerprint
            db.update_processed_email_scoring(
                external_id=stored.external_id,
                importance=score,
                scoring_breakdown=breakdown,
                profile_fingerprint=profile_fingerprint,
            )
            refreshed += 1
        return refreshed
    finally:
        PROFILE_SCORE_REFRESH_LOCK.release()


def build_dashboard(top_n: int = 5) -> DashboardResponse:
    profile = db.get_profile()
    if _gmail_connected():
        db.delete_sample_emails()
    refresh_profile_scores(profile, limit=max(200, top_n * 40))
    priority_categories = profile_priority_categories(profile)
    deprioritize_categories = profile_deprioritize_categories(profile)

    top_candidates = _exclude_legacy_sample_rows(
        _dedupe_by_external_id(db.list_top_important(limit=max(40, top_n * 10)))
    )
    top_important = [
        email
        for email in top_candidates
        if _is_dashboard_priority_email(
            email,
            profile,
            priority_categories=priority_categories,
            deprioritize_categories=deprioritize_categories,
        )
        and email.metadata.importance >= 6.8
    ][:top_n]

    if len(top_important) < top_n:
        fallback = [
            email
            for email in top_candidates
            if email.external_id not in {item.external_id for item in top_important}
            and email.metadata.importance >= 6.5
            and email.metadata.category not in deprioritize_categories
            and not email.metadata.is_bulk
            and email.metadata.category not in NOISY_DASHBOARD_CATEGORIES
        ]
        top_important.extend(fallback[: max(0, top_n - len(top_important))])

    upcoming_deadlines = []
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=14)
    for email in _exclude_legacy_sample_rows(db.list_with_deadlines(limit=30)):
        if email.metadata.deadline is None:
            continue
        deadline = email.metadata.deadline
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if now <= deadline <= horizon:
            if _is_dashboard_priority_email(
                email,
                profile,
                priority_categories=priority_categories,
                deprioritize_categories=deprioritize_categories,
            ) and email.metadata.importance >= 6.5:
                upcoming_deadlines.append(email)
    upcoming_events = []
    for email in _exclude_legacy_sample_rows(db.list_with_events(limit=30)):
        if email.metadata.event_date is None:
            continue
        event_date = email.metadata.event_date
        if event_date.tzinfo is None:
            event_date = event_date.replace(tzinfo=timezone.utc)
        if now <= event_date <= horizon:
            if _is_dashboard_priority_email(
                email,
                profile,
                priority_categories=priority_categories,
                deprioritize_categories=deprioritize_categories,
            ) and email.metadata.importance >= 6.2:
                upcoming_events.append(email)

    job_updates = [
        email
        for email in _exclude_legacy_sample_rows(_dedupe_by_external_id(db.list_by_category("job", limit=30)))
        if not email.metadata.is_bulk and email.metadata.importance >= 6.5
    ][:10]

    excluded_ids = {email.external_id for email in top_important}
    excluded_ids.update(email.external_id for email in job_updates)
    action_required = [
        email
        for email in _exclude_legacy_sample_rows(_dedupe_by_external_id(db.list_action_required(limit=40)))
        if email.external_id not in excluded_ids
        and _is_dashboard_priority_email(
            email,
            profile,
            priority_categories=priority_categories,
            deprioritize_categories=deprioritize_categories,
        )
        and email.metadata.importance >= 6.5
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
    return answer_query(query, ranked, profile=db.get_profile())


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


def _normalize_gmail_sync_scope(
    query: str | None, label_ids: list[str] | None
) -> tuple[str | None, list[str]]:
    normalized_query = (query or "").strip() or None
    if label_ids is None:
        normalized_labels = [] if normalized_query else ["INBOX"]
    else:
        normalized_labels = sorted(
            {
                label.strip()
                for label in label_ids
                if isinstance(label, str) and label.strip()
            }
        )
    return normalized_query, normalized_labels


def _gmail_sync_scope_key(query: str | None, label_ids: list[str]) -> str:
    return json.dumps(
        {"query": query or "", "label_ids": label_ids},
        sort_keys=True,
        separators=(",", ":"),
    )


def _reuse_existing_processing(
    *,
    existing_record: dict[str, object],
    email: EmailIngestItem,
    cleaned_body: str,
    content_fingerprint: str,
    gmail_message_id: str | None,
    gmail_thread_id: str | None,
    profile_fingerprint: str,
) -> bool:
    existing_email = existing_record["email"]
    if not isinstance(existing_email, ProcessedEmail):
        return False
    existing_embedding = existing_record["embedding"]
    if not isinstance(existing_embedding, list):
        return False

    metadata = existing_email.metadata
    if (
        existing_email.content_fingerprint != content_fingerprint
        or metadata.prompt_version != EMAIL_EXTRACTION_PROMPT_VERSION
        or metadata.processing_version != PROCESSING_VERSION
        or metadata.profile_fingerprint != profile_fingerprint
        or metadata.ai_source != "openai"
    ):
        return False

    db.upsert_processed_email(
        external_id=email.external_id,
        from_email=email.from_email,
        from_name=email.from_name,
        subject=email.subject,
        body=email.body,
        cleaned_body=cleaned_body,
        received_at=email.received_at,
        unread=email.unread,
        metadata=metadata,
        embedding=[float(x) for x in existing_embedding],
        gmail_message_id=gmail_message_id,
        gmail_thread_id=gmail_thread_id,
        content_fingerprint=content_fingerprint,
        last_processed_at=existing_email.last_processed_at,
        last_synced_at=datetime.now(timezone.utc),
    )
    return True


def sync_connected_gmail(
    *,
    max_messages: int = 150,
    query: str | None = None,
    label_ids: list[str] | None = None,
    clear_non_gmail: bool = False,
    backfill: bool = False,
    reset_backfill: bool = False,
    sync_until_complete: bool = False,
) -> GmailSyncResult:
    if clear_non_gmail:
        db.delete_non_gmail_emails()

    normalized_query, normalized_labels = _normalize_gmail_sync_scope(query, label_ids)
    scope_key = _gmail_sync_scope_key(normalized_query, normalized_labels)
    use_backfill_cursor = backfill or sync_until_complete

    if use_backfill_cursor and reset_backfill:
        db.delete_gmail_sync_cursor(scope_key=scope_key)

    backfill_complete = False
    page_token: str | None = None
    if use_backfill_cursor:
        cursor_state = db.get_gmail_sync_cursor(scope_key)
        if cursor_state:
            backfill_complete = bool(cursor_state["is_complete"])
            page_token = None if backfill_complete else cursor_state.get("next_page_token")

    profile = db.get_profile()
    profile_fingerprint = profile_processing_fingerprint(profile)
    ingested = 0
    seen_message_ids: set[str] = set()
    has_more = False

    while sync_until_complete or ingested < max_messages:
        remaining = max_messages - ingested
        page_size = 50 if sync_until_complete else min(50, remaining)
        if page_size <= 0:
            break
        message_ids, next_page_token = list_gmail_message_ids(
            max_results=page_size,
            page_token=page_token,
            query=normalized_query,
            label_ids=normalized_labels,
        )
        if not message_ids:
            if use_backfill_cursor and not backfill_complete:
                db.upsert_gmail_sync_cursor(
                    scope_key=scope_key,
                    next_page_token=None,
                    is_complete=True,
                )
                backfill_complete = True
            has_more = False
            break

        for message_id in message_ids:
            if message_id in seen_message_ids:
                continue
            seen_message_ids.add(message_id)
            detail = get_gmail_message_detail(message_id)
            ingest_item = _gmail_detail_to_ingest_item(detail)
            cleaned = clean_email_body(ingest_item.body)
            fingerprint = build_content_fingerprint(ingest_item, cleaned)
            existing = db.get_processed_email_record(ingest_item.external_id)
            reused = False
            if existing:
                reused = _reuse_existing_processing(
                    existing_record=existing,
                    email=ingest_item,
                    cleaned_body=cleaned,
                    content_fingerprint=fingerprint,
                    gmail_message_id=detail.id,
                    gmail_thread_id=detail.thread_id,
                    profile_fingerprint=profile_fingerprint,
                )
            if not reused:
                process_email(
                    ingest_item,
                    profile,
                    gmail_message_id=detail.id,
                    gmail_thread_id=detail.thread_id,
                    cleaned_body=cleaned,
                    content_fingerprint=fingerprint,
                )
            ingested += 1
            if not sync_until_complete and ingested >= max_messages:
                break

        if use_backfill_cursor and not backfill_complete:
            db.upsert_gmail_sync_cursor(
                scope_key=scope_key,
                next_page_token=next_page_token,
                is_complete=not bool(next_page_token),
            )
            backfill_complete = not bool(next_page_token)

        has_more = bool(next_page_token)
        if not next_page_token:
            break
        if not sync_until_complete and ingested >= max_messages:
            break
        page_token = next_page_token

    db.set_runtime_state("last_successful_sync_at", datetime.now(timezone.utc).isoformat())
    return GmailSyncResult(
        ingested=ingested,
        has_more=has_more,
        backfill_complete=backfill_complete if use_backfill_cursor else None,
    )


def _matches_dashboard_sender(email: ProcessedEmail, profile: UserProfile) -> bool:
    preferences = normalize_important_sender_preferences(profile.important_senders)
    if not preferences:
        return False

    from_email = email.from_email.lower()
    if "recruiters" in preferences and any(
        token in from_email for token in ("recruit", "talent", "jobs", "careers")
    ):
        return not email.metadata.is_bulk
    if "professors" in preferences and ".edu" in from_email:
        return True
    if "companies" in preferences and not email.metadata.is_bulk:
        return True

    for value in preferences:
        if value in {"recruiters", "professors", "companies"}:
            continue
        if value and value in from_email:
            return True
    return False


def _looks_noisy_dashboard_marketing(email: ProcessedEmail) -> bool:
    text = f"{email.subject} {email.metadata.summary}".lower()
    return any(term in text for term in NOISY_DASHBOARD_TERMS)


def _is_dashboard_priority_email(
    email: ProcessedEmail,
    profile: UserProfile,
    *,
    priority_categories: set[str],
    deprioritize_categories: set[str],
) -> bool:
    category = email.metadata.category

    if category in deprioritize_categories:
        return False
    if category in NOISY_DASHBOARD_CATEGORIES:
        return category in priority_categories and not email.metadata.is_bulk
    if _looks_noisy_dashboard_marketing(email) and category not in priority_categories:
        return False
    if category in priority_categories:
        return not email.metadata.is_bulk or _matches_dashboard_sender(email, profile)
    if _matches_dashboard_sender(email, profile) and email.metadata.action_required:
        return True
    return email.metadata.importance >= 8.8 and email.metadata.action_required and not email.metadata.is_bulk
