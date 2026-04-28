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


def test_clean_email_body_strips_html_css_boilerplate() -> None:
    body = """
    <style>
      body { margin:0; padding:0; }
      .wrapper { font-family: Arial; }
    </style>
    <div>The latest jobs picked for you!</div>
    <a href="https://example.com/jobs">View all jobs</a>
    """
    cleaned = clean_email_body(body)
    assert "font-family" not in cleaned.lower()
    assert "margin:0" not in cleaned.lower()
    assert "The latest jobs picked for you!" in cleaned
    assert "https://example.com/jobs" in cleaned


def test_clean_email_body_strips_css_fragments_without_style_block() -> None:
    body = (
        "The Morning: A near miss (max-width:600px) (max-width:480px) "
        ".css-nanfcg:hover .css-63f6sn text-decoration:none!important; padding:0!important; "
        "Daily briefing and top stories."
    )
    cleaned = clean_email_body(body)
    lower = cleaned.lower()
    assert "max-width" not in lower
    assert "text-decoration" not in lower
    assert "padding:0" not in lower
    assert "css-nanfcg:hover" not in lower
    assert ".css-63f6sn" not in lower
    assert "daily briefing and top stories" in lower
