"""SQLite storage layer for email index."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np


SCHEMA = """
CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY,
    file_path TEXT UNIQUE NOT NULL,
    file_hash TEXT NOT NULL,
    subject TEXT,
    date TEXT,
    from_addr TEXT,
    from_name TEXT,
    to_addrs TEXT,
    message_id TEXT,
    in_reply_to TEXT,
    markdown TEXT,
    indexed_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS thread_messages (
    id INTEGER PRIMARY KEY,
    email_id INTEGER REFERENCES emails(id) ON DELETE CASCADE,
    position INTEGER,
    from_addr TEXT,
    from_name TEXT,
    sent_date TEXT,
    body_text TEXT,
    is_expert BOOLEAN DEFAULT FALSE,
    embedding BLOB
);

CREATE TABLE IF NOT EXISTS experts (
    email_addr TEXT PRIMARY KEY,
    name TEXT,
    weight REAL DEFAULT 2.0
);

CREATE INDEX IF NOT EXISTS idx_email_file ON emails(file_path);
CREATE INDEX IF NOT EXISTS idx_msg_email ON thread_messages(email_id);
CREATE INDEX IF NOT EXISTS idx_msg_from ON thread_messages(from_addr);
"""


@dataclass
class StoredMessage:
    id: int
    email_id: int
    position: int
    from_addr: str
    from_name: str
    sent_date: str
    body_text: str
    is_expert: bool
    embedding: np.ndarray | None


@dataclass
class StoredEmail:
    id: int
    file_path: str
    subject: str
    date: str
    from_name: str
    markdown: str


class Store:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def get_file_hashes(self) -> dict[str, str]:
        """Return {file_path: file_hash} for all indexed emails."""
        rows = self.conn.execute("SELECT file_path, file_hash FROM emails").fetchall()
        return dict(rows)

    def upsert_email(self, parsed, markdown: str) -> int:
        """Insert or update an email record. Returns the email id."""
        cur = self.conn.execute(
            """INSERT INTO emails (file_path, file_hash, subject, date,
                   from_addr, from_name, to_addrs, message_id, in_reply_to, markdown)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(file_path) DO UPDATE SET
                   file_hash=excluded.file_hash, subject=excluded.subject,
                   date=excluded.date, from_addr=excluded.from_addr,
                   from_name=excluded.from_name, to_addrs=excluded.to_addrs,
                   message_id=excluded.message_id, in_reply_to=excluded.in_reply_to,
                   markdown=excluded.markdown, indexed_at=CURRENT_TIMESTAMP
            """,
            (parsed.file_path, parsed.file_hash, parsed.subject, parsed.date,
             parsed.from_addr, parsed.from_name, json.dumps(parsed.to_addrs),
             parsed.message_id, parsed.in_reply_to, markdown),
        )
        # Get the id
        row = self.conn.execute(
            "SELECT id FROM emails WHERE file_path = ?", (parsed.file_path,)
        ).fetchone()
        return row[0]

    def upsert_messages(self, email_id: int, messages: list, embeddings: list[np.ndarray], experts: set[str]):
        """Replace all thread messages for an email."""
        self.conn.execute("DELETE FROM thread_messages WHERE email_id = ?", (email_id,))
        for msg, emb in zip(messages, embeddings):
            is_expert = msg.from_addr.lower() in experts if msg.from_addr else False
            emb_blob = emb.tobytes() if emb is not None else None
            self.conn.execute(
                """INSERT INTO thread_messages
                   (email_id, position, from_addr, from_name, sent_date, body_text, is_expert, embedding)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (email_id, msg.position, msg.from_addr, msg.from_name,
                 msg.sent_date, msg.body, is_expert, emb_blob),
            )

    def commit(self):
        self.conn.commit()

    def get_email(self, email_id: int) -> StoredEmail | None:
        row = self.conn.execute(
            "SELECT id, file_path, subject, date, from_name, markdown FROM emails WHERE id = ?",
            (email_id,),
        ).fetchone()
        if row:
            return StoredEmail(*row)
        return None

    def get_all_messages_with_embeddings(self) -> list[StoredMessage]:
        """Load all thread messages that have embeddings."""
        rows = self.conn.execute(
            """SELECT id, email_id, position, from_addr, from_name,
                      sent_date, body_text, is_expert, embedding
               FROM thread_messages WHERE embedding IS NOT NULL"""
        ).fetchall()
        results = []
        for r in rows:
            emb = np.frombuffer(r[8], dtype=np.float32) if r[8] else None
            results.append(StoredMessage(
                id=r[0], email_id=r[1], position=r[2],
                from_addr=r[3], from_name=r[4], sent_date=r[5],
                body_text=r[6], is_expert=bool(r[7]), embedding=emb,
            ))
        return results

    def get_experts(self) -> list[tuple[str, str]]:
        """Return list of (email, name) for all experts."""
        return self.conn.execute("SELECT email_addr, name FROM experts").fetchall()

    def add_expert(self, email_addr: str, name: str, weight: float = 2.0):
        self.conn.execute(
            "INSERT OR REPLACE INTO experts (email_addr, name, weight) VALUES (?, ?, ?)",
            (email_addr.lower(), name, weight),
        )
        self.conn.commit()

    def remove_expert(self, email_addr: str):
        self.conn.execute("DELETE FROM experts WHERE email_addr = ?", (email_addr.lower(),))
        self.conn.commit()

    def get_expert_emails(self) -> set[str]:
        """Return set of expert email addresses (lowercase)."""
        rows = self.conn.execute("SELECT email_addr FROM experts").fetchall()
        return {r[0].lower() for r in rows}

    def get_stats(self) -> dict:
        email_count = self.conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
        msg_count = self.conn.execute("SELECT COUNT(*) FROM thread_messages").fetchone()[0]
        expert_msg_count = self.conn.execute(
            "SELECT COUNT(*) FROM thread_messages WHERE is_expert = 1"
        ).fetchone()[0]
        expert_count = self.conn.execute("SELECT COUNT(*) FROM experts").fetchone()[0]
        return {
            "emails": email_count,
            "thread_messages": msg_count,
            "expert_messages": expert_msg_count,
            "experts": expert_count,
        }
