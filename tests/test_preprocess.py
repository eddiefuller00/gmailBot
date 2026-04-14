from __future__ import annotations

from app.preprocess import clean_email_body


def test_clean_email_body_strips_thread_tail() -> None:
    body = (
        "Hi there,\nPlease submit by Friday.\n\n"
        "On Tue, Apr 12, Someone wrote:\nOlder thread content"
    )
    cleaned = clean_email_body(body)
    assert "Older thread content" not in cleaned
    assert "submit by Friday" in cleaned

