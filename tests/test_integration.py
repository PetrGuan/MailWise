"""Integration test: index synthetic EMLs then search them."""
from __future__ import annotations

import textwrap
from pathlib import Path

from email_issue_indexer.embeddings import EmbeddingEngine
from email_issue_indexer.indexer import index_directory
from email_issue_indexer.search import find_similar
from email_issue_indexer.store import Store


def _write_eml(directory: Path, filename: str, subject: str,
               from_addr: str, body: str) -> Path:
    """Write a synthetic EML file."""
    eml = textwrap.dedent(f"""\
        From: {from_addr}
        To: support@example.com
        Subject: {subject}
        Date: Mon, 10 Mar 2025 14:30:00 +0000
        Message-ID: <{filename}@example.com>
        MIME-Version: 1.0
        Content-Type: text/plain; charset="utf-8"

        {body}
    """)
    path = directory / filename
    path.write_text(eml, encoding="utf-8")
    return path


class TestIndexThenSearch:
    def test_full_pipeline(self, tmp_path, embedding_engine):
        # Setup
        eml_dir = tmp_path / "emails"
        eml_dir.mkdir()
        md_dir = tmp_path / "markdown"
        db_path = tmp_path / "test.db"
        store = Store(db_path)

        # Write synthetic EMLs
        _write_eml(eml_dir, "timeout.eml",
                   "Database timeout on reporting queries",
                   "alice@example.com",
                   "Reports are timing out since the schema migration yesterday.")
        _write_eml(eml_dir, "sync.eml",
                   "Sync failure after server update",
                   "bob@example.com",
                   "Mailbox sync is failing for EMEA users with error 0x800CCC0E.")

        # Index
        result = index_directory(
            eml_dir, store, embedding_engine,
            md_dir=md_dir, batch_size=10, max_workers=1, verbose=False,
        )
        assert result["processed"] == 2
        assert result["errors"] == 0

        # Verify stats
        stats = store.get_stats()
        assert stats["emails"] == 2
        assert stats["thread_messages"] >= 2

        # Verify markdown files written
        md_files = list(md_dir.glob("*.md"))
        assert len(md_files) == 2

        # Search
        results = find_similar(
            "database performance issues",
            store, embedding_engine, top_k=2,
        )
        assert len(results) > 0
        assert results[0].email.subject == "Database timeout on reporting queries"

        # Re-index should skip unchanged files
        result2 = index_directory(
            eml_dir, store, embedding_engine,
            md_dir=md_dir, batch_size=10, max_workers=1, verbose=False,
        )
        assert result2["processed"] == 0
        assert result2["skipped"] == 2

        store.close()
