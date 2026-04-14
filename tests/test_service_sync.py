from __future__ import annotations

from datetime import datetime, timezone

from app import service
from app.schemas import GmailMessageDetail, UserProfile


def test_sync_connected_gmail_ingests_messages(monkeypatch) -> None:
    monkeypatch.setattr(service.db, "get_profile", lambda: UserProfile())

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

    def fake_process_email(email, profile) -> None:
        assert profile == UserProfile()
        processed_external_ids.append(email.external_id)

    monkeypatch.setattr(service, "process_email", fake_process_email)

    ingested = service.sync_connected_gmail(max_messages=2)

    assert ingested == 2
    assert processed_external_ids == ["gmail:m-1", "gmail:m-2"]
