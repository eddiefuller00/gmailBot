from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.config import ROOT_DIR


LOGS_DIR = ROOT_DIR / "logs"
ASK_INBOX_LOG_PATH = LOGS_DIR / "ask_inbox_session.jsonl"


def initialize_session_logs() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    if ASK_INBOX_LOG_PATH.exists():
        ASK_INBOX_LOG_PATH.unlink()


def log_ask_inbox_interaction(prompt: str, output: str) -> None:
    normalized = prompt.strip()
    normalized_output = output.strip()
    if not normalized or not normalized_output:
        return

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt": normalized,
        "output": normalized_output,
    }
    with ASK_INBOX_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
