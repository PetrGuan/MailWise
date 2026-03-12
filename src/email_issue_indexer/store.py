"""SQLite storage layer for email index — optimized for bulk operations."""
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
    file_mtime REAL,
    file_size INTEGER,
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
        # Performance pragmas
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        self.conn.execute("PRAGMA mmap_size=268435456")  # 256MB mmap
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def get_file_index(self) -> dict[str, tuple[str, float, int]]:
        """Return {file_path: (file_hash, mtime, size)} for fast change detection."""
        rows = self.conn.execute(
            "SELECT file_path, file_hash, file_mtime, file_size FROM emails"
        ).fetchall()
        return {r[0]: (r[1], r[2], r[3]) for r in rows}

    def upsert_email(self, parsed, markdown: str) -> int:
        """Insert or update an email record. Returns the email id."""
        self.conn.execute(
            """INSERT INTO emails (file_path, file_hash, file_mtime, file_size,
                   subject, date, from_addr, from_name, to_addrs,
                   message_id, in_reply_to, markdown)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(file_path) DO UPDATE SET
                   file_hash=excluded.file_hash, file_mtime=excluded.file_mtime,
                   file_size=excluded.file_size, subject=excluded.subject,
                   date=excluded.date, from_addr=excluded.from_addr,
                   from_name=excluded.from_name, to_addrs=excluded.to_addrs,
                   message_id=excluded.message_id, in_reply_to=excluded.in_reply_to,
                   markdown=excluded.markdown, indexed_at=CURRENT_TIMESTAMP
            """,
            (parsed.file_path, parsed.file_hash, parsed.file_mtime, parsed.file_size,
             parsed.subject, parsed.date, parsed.from_addr, parsed.from_name,
             json.dumps(parsed.to_addrs), parsed.message_id, parsed.in_reply_to,
             markdown),
        )
        row = self.conn.execute(
            "SELECT id FROM emails WHERE file_path = ?", (parsed.file_path,)
        ).fetchone()
        return row[0]

    def upsert_messages_batch(self, email_id: int, messages: list,
                               embeddings: list[np.ndarray], experts: set[str]):
        """Replace all thread messages for an email using batch insert."""
        self.conn.execute("DELETE FROM thread_messages WHERE email_id = ?", (email_id,))
        rows = []
        for msg, emb in zip(messages, embeddings):
            is_expert = msg.from_addr.lower() in experts if msg.from_addr else False
            emb_blob = emb.tobytes() if emb is not None else None
            rows.append((email_id, msg.position, msg.from_addr, msg.from_name,
                         msg.sent_date, msg.body, is_expert, emb_blob))
        if rows:
            self.conn.executemany(
                """INSERT INTO thread_messages
                   (email_id, position, from_addr, from_name, sent_date,
                    body_text, is_expert, embedding)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
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

    def get_search_vectors(self) -> tuple[np.ndarray, np.ndarray, list[int], list[int], list[bool]]:
        """Load embeddings as a single contiguous numpy array for fast search.

        Returns (corpus_matrix, expert_mask, msg_ids, email_ids, is_expert_list).
        Much faster than building StoredMessage objects for 100K+ rows.
        """
        rows = self.conn.execute(
            """SELECT id, email_id, is_expert, embedding
               FROM thread_messages WHERE embedding IS NOT NULL"""
        ).fetchall()

        if not rows:
            return np.array([]), np.array([], dtype=bool), [], [], []

        msg_ids = []
        email_ids = []
        is_expert = []
        embeddings = []

        for r in rows:
            msg_ids.append(r[0])
            email_ids.append(r[1])
            is_expert.append(bool(r[2]))
            embeddings.append(np.frombuffer(r[3], dtype=np.float32))

        corpus = np.stack(embeddings)
        expert_mask = np.array(is_expert, dtype=bool)
        return corpus, expert_mask, msg_ids, email_ids, is_expert

    def get_message_metadata(self, msg_id: int) -> StoredMessage | None:
        """Load a single message's metadata (without embedding)."""
        row = self.conn.execute(
            """SELECT id, email_id, position, from_addr, from_name,
                      sent_date, body_text, is_expert
               FROM thread_messages WHERE id = ?""",
            (msg_id,),
        ).fetchone()
        if row:
            return StoredMessage(
                id=row[0], email_id=row[1], position=row[2],
                from_addr=row[3], from_name=row[4], sent_date=row[5],
                body_text=row[6], is_expert=bool(row[7]), embedding=None,
            )
        return None

    def get_experts(self) -> list[tuple[str, str]]:
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
