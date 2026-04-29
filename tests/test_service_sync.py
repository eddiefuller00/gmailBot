from __future__ import annotations

from datetime import datetime, timezone

from app import service
from app.ai_runtime import AIProcessingError
from app.profile_preferences import profile_processing_fingerprint
from app.schemas import ExtractedMetadata, GmailMessageDetail, UserProfile


def test_sync_connected_gmail_ingests_messages(monkeypatch) -> None:
    monkeypatch.setattr(service.db, "get_profile", lambda: UserProfile())
    monkeypatch.setattr(service.db, "get_processed_email_record", lambda external_id: None)
    monkeypatch.setattr(service.db, "set_runtime_state", lambda key, value: None)

    def fake_list_gmail_message_ids(
        *,
        max_results: int,
        page_token: str | None,
        query: str | None,
        label_ids: list[str] | None,
    ) -> tuple[list[str], str | None]:
        assert max_results <= 50
        assert query is None
        assert label_ids == ["INBOX"]
        if page_token is None:
            return ["m-1", "m-2"], "next-page"
        return ["m-3"], None

    monkeypatch.setattr(service, "list_gmail_message_ids", fake_list_gmail_message_ids)

    details = {
        "m-1": GmailMessageDetail(
            id="m-1",
            thread_id="t-1",
            subject="Interview",
            from_email="talent@company.com",
            from_name="Talent Team",
            received_at=datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc),
            snippet="Pick a slot",
            body_text="Please pick an interview slot.",
            label_ids=["INBOX", "UNREAD"],
            is_unread=True,
        ),
        "m-2": GmailMessageDetail(
            id="m-2",
            thread_id="t-2",
            subject="Newsletter",
            from_email="news@company.com",
            from_name="News",
            received_at=datetime(2026, 4, 14, 11, 0, tzinfo=timezone.utc),
            snippet="Weekly update",
            body_text="Weekly update",
            label_ids=["INBOX"],
            is_unread=False,
        ),
        "m-3": GmailMessageDetail(
            id="m-3",
            thread_id="t-3",
            subject="Ignored due to max",
            from_email="ignored@company.com",
            from_name="Ignored",
            received_at=datetime(2026, 4, 14, 10, 0, tzinfo=timezone.utc),
            snippet="ignore",
            body_text="ignore",
            label_ids=["INBOX"],
            is_unread=False,
        ),
    }

    monkeypatch.setattr(service, "get_gmail_message_detail", lambda message_id: details[message_id])

    processed_external_ids: list[str] = []

    def fake_process_email(email, profile, **kwargs) -> None:
        assert profile == UserProfile()
        processed_external_ids.append(email.external_id)

    monkeypatch.setattr(service, "process_email", fake_process_email)

    result = service.sync_connected_gmail(max_messages=2)

    assert result.ingested == 2
    assert result.has_more is True
    assert result.backfill_complete is None
    assert processed_external_ids == ["gmail:m-1", "gmail:m-2"]


def test_sync_connected_gmail_backfill_resumes_from_saved_cursor(monkeypatch) -> None:
    monkeypatch.setattr(service.db, "get_profile", lambda: UserProfile())
    monkeypatch.setattr(service.db, "get_processed_email_record", lambda external_id: None)
    monkeypatch.setattr(service.db, "set_runtime_state", lambda key, value: None)
    monkeypatch.setattr(
        service.db,
        "get_gmail_sync_cursor",
        lambda scope_key: {
            "scope_key": scope_key,
            "next_page_token": "cursor-2",
            "is_complete": False,
            "updated_at": None,
        },
    )
    monkeypatch.setattr(service.db, "delete_gmail_sync_cursor", lambda scope_key=None: None)
    upserts: list[tuple[str | None, bool]] = []
    monkeypatch.setattr(
        service.db,
        "upsert_gmail_sync_cursor",
        lambda *, scope_key, next_page_token, is_complete: upserts.append(
            (next_page_token, is_complete)
        ),
    )

    def fake_list_gmail_message_ids(
        *,
        max_results: int,
        page_token: str | None,
        query: str | None,
        label_ids: list[str] | None,
    ) -> tuple[list[str], str | None]:
        assert max_results == 2
        assert page_token == "cursor-2"
        assert query is None
        assert label_ids == ["INBOX"]
        return ["m-10", "m-11"], "cursor-3"

    monkeypatch.setattr(service, "list_gmail_message_ids", fake_list_gmail_message_ids)
    monkeypatch.setattr(
        service,
        "get_gmail_message_detail",
        lambda message_id: GmailMessageDetail(
            id=message_id,
            thread_id=f"t-{message_id}",
            subject="Backfill",
            from_email="sender@example.com",
            from_name="Sender",
            received_at=datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc),
            snippet="s",
            body_text="b",
            label_ids=["INBOX"],
            is_unread=False,
        ),
    )

    processed_external_ids: list[str] = []
    monkeypatch.setattr(
        service,
        "process_email",
        lambda email, profile, **kwargs: processed_external_ids.append(email.external_id),
    )

    result = service.sync_connected_gmail(max_messages=2, backfill=True)

    assert result.ingested == 2
    assert result.has_more is True
    assert result.backfill_complete is False
    assert processed_external_ids == ["gmail:m-10", "gmail:m-11"]
    assert upserts == [("cursor-3", False)]


def test_sync_connected_gmail_backfill_complete_syncs_latest_window(monkeypatch) -> None:
    monkeypatch.setattr(service.db, "get_profile", lambda: UserProfile())
    monkeypatch.setattr(service.db, "get_processed_email_record", lambda external_id: None)
    monkeypatch.setattr(service.db, "set_runtime_state", lambda key, value: None)
    monkeypatch.setattr(
        service.db,
        "get_gmail_sync_cursor",
        lambda scope_key: {
            "scope_key": scope_key,
            "next_page_token": None,
            "is_complete": True,
            "updated_at": None,
        },
    )
    monkeypatch.setattr(service.db, "delete_gmail_sync_cursor", lambda scope_key=None: None)
    upserts: list[tuple[str | None, bool]] = []
    monkeypatch.setattr(
        service.db,
        "upsert_gmail_sync_cursor",
        lambda *, scope_key, next_page_token, is_complete: upserts.append(
            (next_page_token, is_complete)
        ),
    )

    def fake_list_gmail_message_ids(
        *,
        max_results: int,
        page_token: str | None,
        query: str | None,
        label_ids: list[str] | None,
    ) -> tuple[list[str], str | None]:
        assert max_results == 1
        assert page_token is None
        assert query is None
        assert label_ids == ["INBOX"]
        return ["m-new"], "next-page"

    monkeypatch.setattr(service, "list_gmail_message_ids", fake_list_gmail_message_ids)
    monkeypatch.setattr(
        service,
        "get_gmail_message_detail",
        lambda message_id: GmailMessageDetail(
            id=message_id,
            thread_id=f"t-{message_id}",
            subject="Recent",
            from_email="sender@example.com",
            from_name="Sender",
            received_at=datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc),
            snippet="s",
            body_text="b",
            label_ids=["INBOX"],
            is_unread=False,
        ),
    )
    monkeypatch.setattr(service, "process_email", lambda email, profile, **kwargs: None)

    result = service.sync_connected_gmail(max_messages=1, backfill=True)

    assert result.ingested == 1
    assert result.has_more is True
    assert result.backfill_complete is True
    assert upserts == []


def test_sync_connected_gmail_until_complete_exhausts_unread_backfill(monkeypatch) -> None:
    monkeypatch.setattr(service.db, "get_profile", lambda: UserProfile())
    monkeypatch.setattr(service.db, "get_processed_email_record", lambda external_id: None)
    monkeypatch.setattr(service.db, "set_runtime_state", lambda key, value: None)
    monkeypatch.setattr(service.db, "get_gmail_sync_cursor", lambda scope_key: None)
    upserts: list[tuple[str | None, bool]] = []
    monkeypatch.setattr(service.db, "delete_gmail_sync_cursor", lambda scope_key=None: None)
    monkeypatch.setattr(
        service.db,
        "upsert_gmail_sync_cursor",
        lambda *, scope_key, next_page_token, is_complete: upserts.append(
            (next_page_token, is_complete)
        ),
    )

    page_calls: list[str | None] = []

    def fake_list_gmail_message_ids(
        *,
        max_results: int,
        page_token: str | None,
        query: str | None,
        label_ids: list[str] | None,
    ) -> tuple[list[str], str | None]:
        assert max_results == 50
        assert query == "is:unread"
        assert label_ids == []
        page_calls.append(page_token)
        if page_token is None:
            return ["m-1", "m-2"], "cursor-2"
        return ["m-3"], None

    monkeypatch.setattr(service, "list_gmail_message_ids", fake_list_gmail_message_ids)
    monkeypatch.setattr(
        service,
        "get_gmail_message_detail",
        lambda message_id: GmailMessageDetail(
            id=message_id,
            thread_id=f"t-{message_id}",
            subject="Unread",
            from_email="sender@example.com",
            from_name="Sender",
            received_at=datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc),
            snippet="s",
            body_text="b",
            label_ids=["INBOX", "UNREAD"],
            is_unread=True,
        ),
    )

    processed_external_ids: list[str] = []
    monkeypatch.setattr(
        service,
        "process_email",
        lambda email, profile, **kwargs: processed_external_ids.append(email.external_id),
    )

    result = service.sync_connected_gmail(
        max_messages=1,
        query="is:unread",
        backfill=True,
        sync_until_complete=True,
    )

    assert result.ingested == 3
    assert result.has_more is False
    assert result.backfill_complete is True
    assert processed_external_ids == ["gmail:m-1", "gmail:m-2", "gmail:m-3"]
    assert page_calls == [None, "cursor-2"]
    assert upserts == [("cursor-2", False), (None, True)]


def test_sync_connected_gmail_reuses_existing_processing_for_unchanged_message(monkeypatch) -> None:
    profile = UserProfile()
    monkeypatch.setattr(service.db, "get_profile", lambda: profile)
    monkeypatch.setattr(service.db, "get_gmail_sync_cursor", lambda scope_key: None)
    monkeypatch.setattr(service.db, "set_runtime_state", lambda key, value: None)
    monkeypatch.setattr(
        service,
        "list_gmail_message_ids",
        lambda **kwargs: (["m-1"], None),
    )

    detail = GmailMessageDetail(
        id="m-1",
        thread_id="t-1",
        subject="Interview",
        from_email="talent@company.com",
        from_name="Talent Team",
        received_at=datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc),
        snippet="Pick a slot",
        body_text="Please pick an interview slot.",
        label_ids=["INBOX", "UNREAD"],
        is_unread=True,
    )
    monkeypatch.setattr(service, "get_gmail_message_detail", lambda message_id: detail)

    ingest_item = service._gmail_detail_to_ingest_item(detail)
    cleaned = service.clean_email_body(ingest_item.body)
    fingerprint = service.build_content_fingerprint(ingest_item, cleaned)
    existing = service.ProcessedEmail(
        id=1,
        external_id="gmail:m-1",
        from_email=ingest_item.from_email,
        from_name=ingest_item.from_name,
        subject=ingest_item.subject,
        body=ingest_item.body,
        cleaned_body=cleaned,
        received_at=ingest_item.received_at,
        unread=True,
        gmail_message_id="m-1",
        gmail_thread_id="t-1",
        content_fingerprint=fingerprint,
        metadata=ExtractedMetadata(
            category="job",
            importance=9.1,
            reason="Recruiter workflow",
            action_required=True,
            summary="Recruiter asks for an interview slot.",
            confidence=0.95,
            action_channel="reply",
                ai_source="openai",
                prompt_version=service.EMAIL_EXTRACTION_PROMPT_VERSION,
                processing_version=service.PROCESSING_VERSION,
                profile_fingerprint=profile_processing_fingerprint(profile),
            ),
        )
    monkeypatch.setattr(
        service.db,
        "get_processed_email_record",
        lambda external_id: {"email": existing, "embedding": [0.1, 0.2]},
    )

    upsert_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        service.db,
        "upsert_processed_email",
        lambda **kwargs: upsert_calls.append(kwargs),
    )

    process_calls: list[str] = []
    monkeypatch.setattr(
        service,
        "process_email",
        lambda email, profile, **kwargs: process_calls.append(email.external_id),
    )

    result = service.sync_connected_gmail(max_messages=1)

    assert result.ingested == 1
    assert result.has_more is False
    assert result.backfill_complete is None
    assert not process_calls
    assert upsert_calls


def test_ensure_processing_versions_current_stops_on_ai_failure(monkeypatch) -> None:
    outdated = [
        service.ProcessedEmail(
            id=1,
            external_id="gmail:m-1",
            from_email="first@example.com",
            from_name="First",
            subject="First",
            body="First body",
            cleaned_body="First body",
            received_at=datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc),
            unread=True,
            metadata=ExtractedMetadata(
                category="job",
                importance=9.0,
                reason="outdated",
                action_required=True,
                summary="First",
                confidence=0.9,
                action_channel="reply",
                ai_source="openai",
                prompt_version="old",
                processing_version="old",
            ),
        ),
        service.ProcessedEmail(
            id=2,
            external_id="gmail:m-2",
            from_email="second@example.com",
            from_name="Second",
            subject="Second",
            body="Second body",
            cleaned_body="Second body",
            received_at=datetime(2026, 4, 14, 11, 0, tzinfo=timezone.utc),
            unread=True,
            metadata=ExtractedMetadata(
                category="job",
                importance=8.5,
                reason="outdated",
                action_required=True,
                summary="Second",
                confidence=0.9,
                action_channel="reply",
                ai_source="openai",
                prompt_version="old",
                processing_version="old",
            ),
        ),
    ]

    monkeypatch.setattr(service.db, "list_outdated_processed_emails", lambda **kwargs: outdated)
    processed_external_ids: list[str] = []

    def fake_process_email(email, profile, **kwargs) -> None:
        processed_external_ids.append(email.external_id)
        raise AIProcessingError("rate limited")

    monkeypatch.setattr(service, "process_email", fake_process_email)

    service.ensure_processing_versions_current(UserProfile(), limit=10)

    assert processed_external_ids == ["gmail:m-1"]
