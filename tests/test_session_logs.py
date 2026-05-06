from __future__ import annotations

import json
from pathlib import Path

from app import session_logs


def test_initialize_session_logs_clears_previous_session_file(monkeypatch, tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    log_path = logs_dir / "ask_inbox_session.jsonl"
    logs_dir.mkdir(parents=True)
    log_path.write_text('{"prompt":"old"}\n', encoding="utf-8")

    monkeypatch.setattr(session_logs, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(session_logs, "ASK_INBOX_LOG_PATH", log_path)

    session_logs.initialize_session_logs()

    assert logs_dir.exists()
    assert not log_path.exists()


def test_log_ask_inbox_interaction_appends_json_line(monkeypatch, tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    log_path = logs_dir / "ask_inbox_session.jsonl"

    monkeypatch.setattr(session_logs, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(session_logs, "ASK_INBOX_LOG_PATH", log_path)

    session_logs.log_ask_inbox_interaction(
        "Show recruiter emails",
        "The most relevant recruiter thread is Vibrant Frontend Position Follow-up.",
    )

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["prompt"] == "Show recruiter emails"
    assert (
        payload["output"]
        == "The most relevant recruiter thread is Vibrant Frontend Position Follow-up."
    )
    assert "timestamp" in payload
