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


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row["name"]) for row in rows}


def _ensure_column(conn: sqlite3.Connection, table_name: str, definition: str) -> None:
    column_name = definition.split()[0]
    if column_name in _table_columns(conn, table_name):
        return
    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {definition}")


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
                embedding TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        for definition in (
            "confidence REAL NOT NULL DEFAULT 0",
            "is_bulk INTEGER NOT NULL DEFAULT 0",
            "action_channel TEXT NOT NULL DEFAULT 'none'",
            "ai_source TEXT NOT NULL DEFAULT 'openai'",
            "prompt_version TEXT NOT NULL DEFAULT ''",
            "processing_version TEXT NOT NULL DEFAULT ''",
            "gmail_message_id TEXT",
            "gmail_thread_id TEXT",
            "content_fingerprint TEXT",
            "last_processed_at TEXT",
            "last_synced_at TEXT",
        ):
            _ensure_column(conn, "emails", definition)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_emails_received_at ON emails(received_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_emails_importance ON emails(importance DESC)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_category ON emails(category)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_emails_gmail_message_id ON emails(gmail_message_id)"
        )
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gmail_sync_cursor (
                scope_key TEXT PRIMARY KEY,
                next_page_token TEXT,
                is_complete INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_runtime_state (
                key TEXT PRIMARY KEY,
                value TEXT,
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
    gmail_message_id: str | None = None,
    gmail_thread_id: str | None = None,
    content_fingerprint: str | None = None,
    last_processed_at: datetime | None = None,
    last_synced_at: datetime | None = None,
) -> None:
    processed_at = last_processed_at or _utc_now()
    synced_at = last_synced_at or _utc_now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO emails (
                external_id, from_email, from_name, subject, body, cleaned_body, received_at, unread,
                category, importance, reason, action_required, deadline, event_date, company, summary,
                confidence, is_bulk, action_channel, ai_source, prompt_version, processing_version,
                scoring_breakdown, embedding, gmail_message_id, gmail_thread_id, content_fingerprint,
                last_processed_at, last_synced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                confidence=excluded.confidence,
                is_bulk=excluded.is_bulk,
                action_channel=excluded.action_channel,
                ai_source=excluded.ai_source,
                prompt_version=excluded.prompt_version,
                processing_version=excluded.processing_version,
                scoring_breakdown=excluded.scoring_breakdown,
                embedding=excluded.embedding,
                gmail_message_id=excluded.gmail_message_id,
                gmail_thread_id=excluded.gmail_thread_id,
                content_fingerprint=excluded.content_fingerprint,
                last_processed_at=excluded.last_processed_at,
                last_synced_at=excluded.last_synced_at
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
                float(metadata.confidence),
                int(metadata.is_bulk),
                metadata.action_channel,
                metadata.ai_source,
                metadata.prompt_version,
                metadata.processing_version,
                json.dumps(metadata.scoring_breakdown),
                json.dumps(embedding),
                gmail_message_id,
                gmail_thread_id,
                content_fingerprint,
                _to_iso(processed_at),
                _to_iso(synced_at),
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
        confidence=float(row["confidence"] or 0.0),
        is_bulk=bool(row["is_bulk"]),
        action_channel=row["action_channel"],
        ai_source=row["ai_source"],
        prompt_version=row["prompt_version"],
        processing_version=row["processing_version"],
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
        gmail_message_id=row["gmail_message_id"],
        gmail_thread_id=row["gmail_thread_id"],
        content_fingerprint=row["content_fingerprint"],
        last_processed_at=_from_iso(row["last_processed_at"]),
        last_synced_at=_from_iso(row["last_synced_at"]),
        metadata=metadata,
    )


def list_processed_emails(limit: int = 5000) -> list[ProcessedEmail]:
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


def get_processed_email_record(external_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM emails WHERE external_id=?",
            (external_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "email": _row_to_processed_email(row),
        "embedding": json.loads(row["embedding"]),
    }


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


def list_outdated_processed_emails(
    *,
    prompt_version: str,
    processing_version: str,
    limit: int = 200,
) -> list[ProcessedEmail]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM emails
            WHERE prompt_version != ?
               OR processing_version != ?
               OR ai_source != 'openai'
               OR content_fingerprint IS NULL
            ORDER BY last_processed_at ASC, received_at DESC
            LIMIT ?
            """,
            (prompt_version, processing_version, limit),
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


def get_gmail_sync_cursor(scope_key: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT scope_key, next_page_token, is_complete, updated_at
            FROM gmail_sync_cursor
            WHERE scope_key=?
            """,
            (scope_key,),
        ).fetchone()
    if not row:
        return None
    return {
        "scope_key": row["scope_key"],
        "next_page_token": row["next_page_token"],
        "is_complete": bool(row["is_complete"]),
        "updated_at": _from_iso(row["updated_at"]),
    }


def upsert_gmail_sync_cursor(
    *,
    scope_key: str,
    next_page_token: str | None,
    is_complete: bool,
) -> None:
    now = _utc_now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO gmail_sync_cursor(scope_key, next_page_token, is_complete, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(scope_key) DO UPDATE SET
                next_page_token=excluded.next_page_token,
                is_complete=excluded.is_complete,
                updated_at=excluded.updated_at
            """,
            (scope_key, next_page_token, int(is_complete), _to_iso(now)),
        )
        conn.commit()


def delete_gmail_sync_cursor(scope_key: str | None = None) -> None:
    with _connect() as conn:
        if scope_key is None:
            conn.execute("DELETE FROM gmail_sync_cursor")
        else:
            conn.execute(
                "DELETE FROM gmail_sync_cursor WHERE scope_key=?",
                (scope_key,),
            )
        conn.commit()


def set_runtime_state(key: str, value: str | None) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO app_runtime_state(key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value,
                updated_at=excluded.updated_at
            """,
            (key, value, _to_iso(_utc_now())),
        )
        conn.commit()


def get_runtime_state(key: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT key, value, updated_at FROM app_runtime_state WHERE key=?",
            (key,),
        ).fetchone()
    if not row:
        return None
    return {
        "key": row["key"],
        "value": row["value"],
        "updated_at": _from_iso(row["updated_at"]),
    }


def delete_runtime_state(key: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM app_runtime_state WHERE key=?", (key,))
        conn.commit()
