from __future__ import annotations

from app.response_intent import detect_response_intent, is_no_reply_sender


def test_is_no_reply_sender_detects_common_patterns() -> None:
    assert is_no_reply_sender("no-reply@example.com") is True
    assert is_no_reply_sender("DoNotReply@example.com") is True
    assert is_no_reply_sender("alerts@ziprecruiter.com") is True
    assert is_no_reply_sender("emails@emails.efinancialcareers.com") is True
    assert is_no_reply_sender("recruiter@company.com") is False


def test_detect_response_intent_for_link_only_automation() -> None:
    signals = detect_response_intent(
        from_email="no-reply@example.com",
        subject="Account update",
        body=(
            "Click to review your account: https://example.com/a "
            "This mailbox is not monitored."
        ),
    )
    assert signals.no_reply_sender is True
    assert signals.link_only_cta is True
    assert signals.likely_needs_reply is False


def test_detect_response_intent_for_explicit_reply_request() -> None:
    signals = detect_response_intent(
        from_email="recruiter@company.com",
        subject="Interview availability",
        body="Please reply by Friday with your available time slots.",
    )
    assert signals.no_reply_sender is False
    assert signals.link_only_cta is False
    assert signals.explicit_reply_requested is True
    assert signals.likely_needs_reply is True


def test_detect_response_intent_for_single_link_blast() -> None:
    signals = detect_response_intent(
        from_email="alerts@ziprecruiter.com",
        subject="CAI may want to hire you",
        body="<https://www.ziprecruiter.com/jobs/12345>",
    )
    assert signals.no_reply_sender is True
    assert signals.link_only_cta is True
    assert signals.likely_needs_reply is False


def test_detect_response_intent_with_do_not_respond_language() -> None:
    signals = detect_response_intent(
        from_email="updates@example.com",
        subject="Weekly digest",
        body="Please do not respond to this email. View in browser: https://example.com/digest",
    )
    assert signals.no_reply_sender is True
    assert signals.link_only_cta is True
    assert signals.likely_needs_reply is False
