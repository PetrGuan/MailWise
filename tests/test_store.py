"""Tests for SQLite storage layer."""
from __future__ import annotations

import numpy as np

from email_issue_indexer.parser import ParsedEmail, ThreadMessage
from email_issue_indexer.store import Store


def _make_parsed_email(file_path="test.eml", subject="Test Subject",
                       from_addr="jane@example.com", messages=None):
    """Helper to create a ParsedEmail for testing."""
    if messages is None:
        messages = [
            ThreadMessage(
                from_name="Jane Doe", from_addr="jane@example.com",
                sent_date="2025-03-10", to_addrs="support@example.com",
                subject=subject, body="Test body content.", position=0,
            )
        ]
    return ParsedEmail(
        file_path=file_path, file_hash="abc123", file_mtime=1000.0,
        file_size=500, subject=subject, date="2025-03-10",
        from_name="Jane Doe", from_addr=from_addr,
        to_addrs=["support@example.com"], message_id="<msg@example.com>",
        in_reply_to=None, messages=messages,
    )


class TestSchemaCreation:
    def test_creates_tables(self, tmp_store):
        tables = tmp_store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        assert "emails" in table_names
        assert "thread_messages" in table_names
        assert "experts" in table_names


class TestEmailCRUD:
    def test_upsert_and_get_email(self, tmp_store):
        parsed = _make_parsed_email()
        email_id = tmp_store.upsert_email(parsed, "# Test markdown")
        tmp_store.commit()

        email = tmp_store.get_email(email_id)
        assert email is not None
        assert email.subject == "Test Subject"
        assert email.markdown == "# Test markdown"

    def test_upsert_updates_existing(self, tmp_store):
        parsed = _make_parsed_email(subject="Original")
        id1 = tmp_store.upsert_email(parsed, "md1")
        tmp_store.commit()

        parsed2 = _make_parsed_email(subject="Updated")
        id2 = tmp_store.upsert_email(parsed2, "md2")
        tmp_store.commit()

        assert id1 == id2
        email = tmp_store.get_email(id1)
        assert email.subject == "Updated"

    def test_get_nonexistent_email(self, tmp_store):
        assert tmp_store.get_email(9999) is None


class TestMessageBatch:
    def test_upsert_and_get_metadata(self, tmp_store):
        parsed = _make_parsed_email()
        email_id = tmp_store.upsert_email(parsed, "md")

        embedding = np.random.randn(384).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        tmp_store.upsert_messages_batch(
            email_id, parsed.messages, [embedding], set()
        )
        tmp_store.commit()

        msg = tmp_store.get_message_metadata(1)
        assert msg is not None
        assert msg.email_id == email_id
        assert msg.from_addr == "jane@example.com"
        assert msg.body_text == "Test body content."

    def test_expert_flag_set(self, tmp_store):
        parsed = _make_parsed_email()
        email_id = tmp_store.upsert_email(parsed, "md")

        embedding = np.random.randn(384).astype(np.float32)
        tmp_store.upsert_messages_batch(
            email_id, parsed.messages, [embedding],
            experts={"jane@example.com"},
        )
        tmp_store.commit()

        msg = tmp_store.get_message_metadata(1)
        assert msg.is_expert is True


class TestSearchVectors:
    def test_returns_correct_arrays(self, tmp_store):
        parsed = _make_parsed_email()
        email_id = tmp_store.upsert_email(parsed, "md")

        embedding = np.random.randn(384).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        tmp_store.upsert_messages_batch(
            email_id, parsed.messages, [embedding], set()
        )
        tmp_store.commit()

        corpus, expert_mask, msg_ids, email_ids, is_expert = (
            tmp_store.get_search_vectors()
        )
        assert corpus.shape == (1, 384)
        assert expert_mask.shape == (1,)
        assert len(msg_ids) == 1
        assert email_ids[0] == email_id

    def test_empty_store(self, tmp_store):
        corpus, expert_mask, msg_ids, email_ids, is_expert = (
            tmp_store.get_search_vectors()
        )
        assert len(corpus) == 0
        assert len(msg_ids) == 0


class TestFileIndex:
    def test_returns_stored_metadata(self, tmp_store):
        parsed = _make_parsed_email(file_path="/tmp/test.eml")
        tmp_store.upsert_email(parsed, "md")
        tmp_store.commit()

        index = tmp_store.get_file_index()
        assert "/tmp/test.eml" in index
        file_hash, mtime, size = index["/tmp/test.eml"]
        assert file_hash == "abc123"
        assert mtime == 1000.0
        assert size == 500


class TestExperts:
    def test_add_and_list(self, tmp_store):
        tmp_store.add_expert("alice@example.com", "Alice")
        experts = tmp_store.get_experts()
        assert len(experts) == 1
        assert experts[0] == ("alice@example.com", "Alice")

    def test_remove(self, tmp_store):
        tmp_store.add_expert("alice@example.com", "Alice")
        tmp_store.remove_expert("alice@example.com")
        assert tmp_store.get_experts() == []

    def test_get_expert_emails_lowercased(self, tmp_store):
        tmp_store.add_expert("Alice@Example.COM", "Alice")
        emails = tmp_store.get_expert_emails()
        assert "alice@example.com" in emails


class TestStats:
    def test_counts(self, tmp_store):
        parsed = _make_parsed_email()
        email_id = tmp_store.upsert_email(parsed, "md")
        embedding = np.random.randn(384).astype(np.float32)
        tmp_store.upsert_messages_batch(
            email_id, parsed.messages, [embedding], set()
        )
        tmp_store.add_expert("x@example.com", "X")
        tmp_store.commit()

        stats = tmp_store.get_stats()
        assert stats["emails"] == 1
        assert stats["thread_messages"] == 1
        assert stats["experts"] == 1
