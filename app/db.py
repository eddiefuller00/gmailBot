from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from app.config import settings
from app.schemas import ExtractedMetadata, ProcessedEmail, UserProfile


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    _ensure_parent_dir(settings.database_path)
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT UNIQUE NOT NULL,
                from_email TEXT NOT NULL,
                from_name TEXT,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                cleaned_body TEXT NOT NULL,
                received_at TEXT NOT NULL,
                unread INTEGER NOT NULL,
                category TEXT NOT NULL,
                importance REAL NOT NULL,
                reason TEXT NOT NULL,
                action_required INTEGER NOT NULL,
                deadline TEXT,
                event_date TEXT,
                company TEXT,
                summary TEXT NOT NULL,
                scoring_breakdown TEXT NOT NULL,
                embedding TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_emails_received_at ON emails(received_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_emails_importance ON emails(importance DESC)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_category ON emails(category)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS google_oauth_state (
                state TEXT PRIMARY KEY,
                expires_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_google_oauth_state_expires_at ON google_oauth_state(expires_at)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS google_oauth_token (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                token_data TEXT NOT NULL,
                is_encrypted INTEGER NOT NULL,
                email TEXT,
                scopes TEXT NOT NULL,
                connected_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def save_profile(profile: UserProfile) -> UserProfile:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO profile(id, data)
            VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET data=excluded.data
            """,
            (profile.model_dump_json(),),
        )
        conn.commit()
    return profile


def get_profile() -> UserProfile:
    with _connect() as conn:
        row = conn.execute("SELECT data FROM profile WHERE id=1").fetchone()
    if not row:
        return UserProfile()
    return UserProfile.model_validate_json(row["data"])


def upsert_processed_email(
    *,
    external_id: str,
    from_email: str,
    from_name: str | None,
    subject: str,
    body: str,
    cleaned_body: str,
    received_at: datetime,
    unread: bool,
    metadata: ExtractedMetadata,
    embedding: list[float],
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO emails (
                external_id, from_email, from_name, subject, body, cleaned_body, received_at, unread,
                category, importance, reason, action_required, deadline, event_date, company, summary,
                scoring_breakdown, embedding
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(external_id) DO UPDATE SET
                from_email=excluded.from_email,
                from_name=excluded.from_name,
                subject=excluded.subject,
                body=excluded.body,
                cleaned_body=excluded.cleaned_body,
                received_at=excluded.received_at,
                unread=excluded.unread,
                category=excluded.category,
                importance=excluded.importance,
                reason=excluded.reason,
                action_required=excluded.action_required,
                deadline=excluded.deadline,
                event_date=excluded.event_date,
                company=excluded.company,
                summary=excluded.summary,
                scoring_breakdown=excluded.scoring_breakdown,
                embedding=excluded.embedding
            """,
            (
                external_id,
                from_email,
                from_name,
                subject,
                body,
                cleaned_body,
                _to_iso(received_at),
                int(unread),
                metadata.category,
                float(metadata.importance),
                metadata.reason,
                int(metadata.action_required),
                _to_iso(metadata.deadline),
                _to_iso(metadata.event_date),
                metadata.company,
                metadata.summary,
                json.dumps(metadata.scoring_breakdown),
                json.dumps(embedding),
            ),
        )
        conn.commit()


def _row_to_processed_email(row: sqlite3.Row) -> ProcessedEmail:
    metadata = ExtractedMetadata(
        category=row["category"],
        importance=float(row["importance"]),
        reason=row["reason"],
        action_required=bool(row["action_required"]),
        deadline=_from_iso(row["deadline"]),
        event_date=_from_iso(row["event_date"]),
        company=row["company"],
        summary=row["summary"],
        scoring_breakdown=json.loads(row["scoring_breakdown"]),
    )
    return ProcessedEmail(
        id=int(row["id"]),
        external_id=row["external_id"],
        from_email=row["from_email"],
        from_name=row["from_name"],
        subject=row["subject"],
        body=row["body"],
        cleaned_body=row["cleaned_body"],
        received_at=datetime.fromisoformat(row["received_at"]),
        unread=bool(row["unread"]),
        metadata=metadata,
    )


def list_processed_emails(limit: int = 200) -> list[ProcessedEmail]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM emails ORDER BY received_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_processed_email(row) for row in rows]


def get_email_vectors(limit: int = 2000) -> list[tuple[ProcessedEmail, list[float]]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM emails ORDER BY received_at DESC LIMIT ?", (limit,)
        ).fetchall()
    results: list[tuple[ProcessedEmail, list[float]]] = []
    for row in rows:
        email = _row_to_processed_email(row)
        vector = json.loads(row["embedding"])
        results.append((email, vector))
    return results


def list_top_important(limit: int) -> list[ProcessedEmail]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM emails ORDER BY importance DESC, received_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_processed_email(row) for row in rows]


def list_by_category(category: str, limit: int = 20) -> list[ProcessedEmail]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM emails
            WHERE category=?
            ORDER BY importance DESC, received_at DESC
            LIMIT ?
            """,
            (category, limit),
        ).fetchall()
    return [_row_to_processed_email(row) for row in rows]


def list_action_required(limit: int = 20) -> list[ProcessedEmail]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM emails
            WHERE action_required=1
            ORDER BY importance DESC, received_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_row_to_processed_email(row) for row in rows]


def list_with_deadlines(limit: int = 20) -> list[ProcessedEmail]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM emails
            WHERE deadline IS NOT NULL
            ORDER BY deadline ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_row_to_processed_email(row) for row in rows]


def list_with_events(limit: int = 20) -> list[ProcessedEmail]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM emails
            WHERE event_date IS NOT NULL
            ORDER BY event_date ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_row_to_processed_email(row) for row in rows]


def count_unread_important(min_importance: float = 7.0) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM emails WHERE unread=1 AND importance>=?",
            (min_importance,),
        ).fetchone()
    return int(row["count"]) if row else 0


def query_rows(sql: str, params: tuple[Any, ...]) -> list[ProcessedEmail]:
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_processed_email(row) for row in rows]


def delete_non_gmail_emails() -> int:
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM emails WHERE external_id NOT LIKE 'gmail:%'"
        )
        conn.commit()
    return int(cursor.rowcount or 0)


def create_google_oauth_state(state: str, expires_at: datetime) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO google_oauth_state(state, expires_at)
            VALUES (?, ?)
            """,
            (state, _to_iso(expires_at)),
        )
        conn.commit()


def consume_google_oauth_state(state: str) -> bool:
    now_iso = _to_iso(_utc_now())
    with _connect() as conn:
        conn.execute(
            "DELETE FROM google_oauth_state WHERE expires_at <= ?",
            (now_iso,),
        )
        row = conn.execute(
            "SELECT state, expires_at FROM google_oauth_state WHERE state=?",
            (state,),
        ).fetchone()
        if not row:
            conn.commit()
            return False

        expires_at = _from_iso(row["expires_at"])
        valid = bool(expires_at and expires_at > _utc_now())
        conn.execute("DELETE FROM google_oauth_state WHERE state=?", (state,))
        conn.commit()
        return valid


def save_google_oauth_token(
    *,
    token_data: str,
    is_encrypted: bool,
    email: str | None,
    scopes: list[str],
) -> None:
    now = _utc_now()
    with _connect() as conn:
        existing = conn.execute(
            "SELECT connected_at FROM google_oauth_token WHERE id=1"
        ).fetchone()
        connected_at = (
            existing["connected_at"] if existing and existing["connected_at"] else _to_iso(now)
        )
        conn.execute(
            """
            INSERT INTO google_oauth_token(
                id, token_data, is_encrypted, email, scopes, connected_at, updated_at
            )
            VALUES (1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                token_data=excluded.token_data,
                is_encrypted=excluded.is_encrypted,
                email=excluded.email,
                scopes=excluded.scopes,
                updated_at=excluded.updated_at
            """,
            (
                token_data,
                int(is_encrypted),
                email,
                json.dumps(scopes),
                connected_at,
                _to_iso(now),
            ),
        )
        conn.commit()


def get_google_oauth_token() -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM google_oauth_token WHERE id=1").fetchone()
    if not row:
        return None

    return {
        "token_data": row["token_data"],
        "is_encrypted": bool(row["is_encrypted"]),
        "email": row["email"],
        "scopes": json.loads(row["scopes"]),
        "connected_at": _from_iso(row["connected_at"]),
        "updated_at": _from_iso(row["updated_at"]),
    }


def clear_google_oauth_token() -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM google_oauth_token WHERE id=1")
        conn.commit()
