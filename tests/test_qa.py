from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app import qa
from app.schemas import ExtractedMetadata, ProcessedEmail, UserProfile


def _make_email(
    *,
    eid: str,
    subject: str,
    from_email: str,
    category: str,
    action_required: bool = False,
    deadline: datetime | None = None,
    event_date: datetime | None = None,
) -> ProcessedEmail:
    return ProcessedEmail(
        id=1,
        external_id=eid,
        from_email=from_email,
        from_name=None,
        subject=subject,
        body=subject,
        cleaned_body=subject,
        received_at=datetime.now(timezone.utc),
        unread=True,
        metadata=ExtractedMetadata(
            category=category,  # type: ignore[arg-type]
            importance=9.0,
            reason="test",
            action_required=action_required,
            deadline=deadline,
            event_date=event_date,
            summary=subject,
            confidence=0.95,
            action_channel="reply" if action_required else "none",
            ai_source="openai",
            prompt_version="email-extraction-v2",
            processing_version="processing-v2",
        ),
    )


class _FakeCompletion:
    def __init__(self, payload: dict[str, object]):
        self.choices = [
            type(
                "Choice",
                (),
                {"message": type("Message", (), {"content": json.dumps(payload)})()},
            )()
        ]


class _FakeClient:
    def __init__(self, payload: dict[str, object]):
        self.chat = type(
            "Chat",
            (),
            {
                "completions": type(
                    "Completions",
                    (),
                    {"create": lambda *args, **kwargs: _FakeCompletion(payload)},
                )()
            },
        )()


def test_parse_qa_payload_uses_citations() -> None:
    emails = [
        _make_email(
            eid="gmail:1",
            subject="Interview scheduling",
            from_email="talent@company.com",
            category="job",
            action_required=True,
        ),
        _make_email(
            eid="gmail:2",
            subject="Weekly newsletter",
            from_email="news@company.com",
            category="newsletter",
        ),
    ]
    parsed = qa.parse_qa_payload(
        {
            "answer": "Handle the interview email first.",
            "citations": ["gmail:1"],
        },
        ranked_emails=emails,
    )
    assert parsed is not None
    answer, citations, supporting = parsed
    assert "interview" in answer.lower()
    assert citations == ["gmail:1"]
    assert supporting[0].external_id == "gmail:1"


def test_answer_query_returns_cited_openai_response(monkeypatch) -> None:
    soon = datetime.now(timezone.utc) + timedelta(days=2)
    emails = [
        _make_email(
            eid="gmail:1",
            subject="Interview scheduling",
            from_email="talent@company.com",
            category="job",
            action_required=True,
            deadline=soon,
        ),
        _make_email(
            eid="gmail:2",
            subject="Weekly newsletter",
            from_email="news@company.com",
            category="newsletter",
        ),
    ]
    monkeypatch.setattr(
        qa,
        "get_openai_client",
        lambda: _FakeClient(
            {
                "answer": "The interview scheduling email has the most urgent deadline this week.",
                "citations": ["gmail:1"],
            }
        ),
    )
    monkeypatch.setattr(qa, "record_ai_success", lambda: None)

    response = qa.answer_query(
        "What deadlines do I have this week?",
        emails,
        profile=UserProfile(priorities=["jobs"]),
    )

    assert response.answer_mode == "openai_rag"
    assert response.citations == ["gmail:1"]
    assert response.supporting_emails[0].external_id == "gmail:1"
