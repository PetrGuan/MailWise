"""Tests for semantic search with deduplication and formatting."""
from __future__ import annotations

import numpy as np

from email_issue_indexer.parser import ParsedEmail, ThreadMessage
from email_issue_indexer.search import find_similar, format_results, SearchResult
from email_issue_indexer.store import StoredEmail, StoredMessage
from email_issue_indexer.markdown import to_markdown


def _index_synthetic_emails(store, engine):
    """Index 3 synthetic emails into the store with real embeddings."""
    emails_data = [
        ("db-timeout.eml", "Database timeout on queries",
         "alice@example.com", "Alice",
         "The reporting queries are timing out after the schema migration."),
        ("sync-failure.eml", "Sync failure in EMEA region",
         "bob@example.com", "Bob",
         "Users in EMEA cannot sync their mailboxes since the server update."),
        ("auth-error.eml", "Authentication failures after password reset",
         "carol@example.com", "Carol",
         "Multiple users reporting 401 errors after the forced password reset."),
    ]

    for file_path, subject, from_addr, from_name, body in emails_data:
        messages = [
            ThreadMessage(
                from_name=from_name, from_addr=from_addr,
                sent_date="2025-03-10", to_addrs="support@example.com",
                subject=subject, body=body, position=0,
            )
        ]
        parsed = ParsedEmail(
            file_path=file_path, file_hash="hash_" + file_path,
            file_mtime=1000.0, file_size=500,
            subject=subject, date="2025-03-10",
            from_name=from_name, from_addr=from_addr,
            to_addrs=["support@example.com"],
            message_id=f"<{file_path}@example.com>",
            in_reply_to=None, messages=messages,
        )
        md = to_markdown(parsed)
        email_id = store.upsert_email(parsed, md)

        text = f"{subject}\n\n{body}"
        embedding = engine.embed(text[:2000])
        store.upsert_messages_batch(email_id, messages, [embedding], set())

    store.commit()


class TestFindSimilar:
    def test_returns_ranked_results(self, tmp_store, embedding_engine):
        _index_synthetic_emails(tmp_store, embedding_engine)
        results = find_similar(
            "database query performance issues",
            tmp_store, embedding_engine, top_k=3,
        )
        assert len(results) > 0
        # First result should be the database-related email
        assert "timeout" in results[0].email.subject.lower() or \
               "database" in results[0].email.subject.lower()

    def test_expert_only_filter(self, tmp_store, embedding_engine):
        _index_synthetic_emails(tmp_store, embedding_engine)
        # Mark alice as expert
        tmp_store.add_expert("alice@example.com", "Alice")
        # Update is_expert for alice's messages
        tmp_store.conn.execute(
            "UPDATE thread_messages SET is_expert = 1 WHERE from_addr = 'alice@example.com'"
        )
        tmp_store.commit()

        results = find_similar(
            "any query", tmp_store, embedding_engine,
            top_k=10, expert_only=True,
        )
        for r in results:
            assert r.message.is_expert

    def test_empty_store_returns_empty(self, tmp_store, embedding_engine):
        results = find_similar("test", tmp_store, embedding_engine)
        assert results == []


class TestFormatResults:
    def test_no_results(self):
        assert format_results([]) == "No similar issues found."

    def test_formats_with_score_and_subject(self):
        result = SearchResult(
            message=StoredMessage(
                id=1, email_id=1, position=0,
                from_addr="alice@example.com", from_name="Alice",
                sent_date="2025-03-10", body_text="Some body text.",
                is_expert=True, embedding=None,
            ),
            email=StoredEmail(
                id=1, file_path="test.eml",
                subject="Test Subject", date="2025-03-10",
                from_name="Alice", markdown="",
            ),
            score=0.856,
        )
        output = format_results([result])
        assert "0.856" in output
        assert "Test Subject" in output
        assert "[Expert]" in output
        assert "Alice" in output

    def test_show_body_preview(self):
        result = SearchResult(
            message=StoredMessage(
                id=1, email_id=1, position=0,
                from_addr="a@example.com", from_name="A",
                sent_date="2025-03-10", body_text="Detailed body for preview.",
                is_expert=False, embedding=None,
            ),
            email=StoredEmail(
                id=1, file_path="t.eml", subject="S",
                date="2025-03-10", from_name="A", markdown="",
            ),
            score=0.5,
        )
        output = format_results([result], show_body=True)
        assert "Detailed body for preview." in output
