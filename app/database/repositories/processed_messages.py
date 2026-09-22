"""
Phase 1 storage: superseded by Phase 2's Postgres repositories.
Left here for reference/rollback only — no longer imported by processor.py or main.py.

See app/database/repositories/emails.py for the Phase 2 replacement.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_messages (
    message_id TEXT PRIMARY KEY,
    processed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    message_id TEXT PRIMARY KEY,
    thread_id TEXT,
    subject TEXT,
    sender TEXT,
    summary TEXT,
    reason TEXT,
    action_items TEXT,
    importance_score INTEGER,
    urgency TEXT,
    category TEXT,
    requires_action INTEGER,
    deadline TEXT,
    notification_tier TEXT,
    notified INTEGER,
    received_at TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL,
    feedback_type TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


@dataclass
class NotificationRecord:
    message_id: str
    thread_id: str
    subject: str
    sender: str
    summary: str
    reason: str
    action_items: list[str]
    importance_score: int
    urgency: str
    category: str
    requires_action: bool
    deadline: Optional[str]
    notification_tier: str
    notified: bool
    received_at: str


class Store:
    """Single SQLite-backed store for Phase 1 idempotency + notification log + feedback."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- idempotency -----------------------------------------------------

    def has_processed(self, message_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM processed_messages WHERE message_id = ?", (message_id,)
            ).fetchone()
            return row is not None

    def mark_processed(self, message_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO processed_messages (message_id, processed_at) VALUES (?, ?)",
                (message_id, datetime.now(timezone.utc).isoformat()),
            )

    # --- notification log --------------------------------------------------

    def log_notification(self, record: NotificationRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO notifications (
                    message_id, thread_id, subject, sender, summary, reason,
                    action_items, importance_score, urgency, category,
                    requires_action, deadline, notification_tier, notified,
                    received_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.message_id,
                    record.thread_id,
                    record.subject,
                    record.sender,
                    record.summary,
                    record.reason,
                    "|".join(record.action_items),
                    record.importance_score,
                    record.urgency,
                    record.category,
                    int(record.requires_action),
                    record.deadline,
                    record.notification_tier,
                    int(record.notified),
                    record.received_at,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def recent_notifications(self, *, only_notified: bool = False, limit: int = 20) -> list[sqlite3.Row]:
        query = "SELECT * FROM notifications"
        if only_notified:
            query += " WHERE notified = 1"
        query += " ORDER BY created_at DESC LIMIT ?"
        with self._connect() as conn:
            return conn.execute(query, (limit,)).fetchall()

    def notifications_since(self, since_iso: str) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM notifications WHERE received_at >= ? ORDER BY received_at DESC",
                (since_iso,),
            ).fetchall()

    def get_notification(self, message_id: str) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM notifications WHERE message_id = ?", (message_id,)
            ).fetchone()

    # --- feedback ----------------------------------------------------------

    def record_feedback(self, message_id: str, feedback_type: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO feedback (message_id, feedback_type, created_at) VALUES (?, ?, ?)",
                (message_id, feedback_type, datetime.now(timezone.utc).isoformat()),
            )
