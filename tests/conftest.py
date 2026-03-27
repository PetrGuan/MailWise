"""Shared test fixtures — synthetic EML files and temp databases."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a clean temporary directory."""
    return tmp_path


@pytest.fixture
def tmp_store(tmp_path):
    """Fresh SQLite Store in a temp directory, auto-closed."""
    from email_issue_indexer.store import Store

    store = Store(tmp_path / "test.db")
    yield store
    store.close()


@pytest.fixture
def sample_eml_path(tmp_path):
    """Write a simple single-message synthetic EML and return its path."""
    eml_content = textwrap.dedent("""\
        From: Jane Doe <jane.doe@example.com>
        To: support@example.com
        Subject: Sync failure after migration
        Date: Mon, 10 Mar 2025 14:30:00 +0000
        Message-ID: <msg001@example.com>
        MIME-Version: 1.0
        Content-Type: text/plain; charset="utf-8"

        Hi team,

        After the migration last night, sync is failing for all users
        in the EMEA region. Error code 0x800CCC0E.

        Please investigate urgently.

        Thanks,
        Jane
    """)
    path = tmp_path / "sample.eml"
    path.write_text(eml_content, encoding="utf-8")
    return path


@pytest.fixture
def threaded_eml_path(tmp_path):
    """Write an Outlook-style threaded EML with From:/Sent: inline replies."""
    eml_content = textwrap.dedent("""\
        From: Alice Smith <alice@example.com>
        To: support@example.com
        Subject: RE: Database timeout on reporting queries
        Date: Tue, 11 Mar 2025 09:00:00 +0000
        Message-ID: <msg002@example.com>
        In-Reply-To: <msg001@example.com>
        MIME-Version: 1.0
        Content-Type: text/plain; charset="utf-8"

        I've applied the index fix, should be resolved now.

        ________________________________
        From: Bob Chen <bob@example.com>
        Sent: Tuesday, March 11, 2025 8:30 AM
        To: support@example.com
        Subject: RE: Database timeout on reporting queries

        Seeing the same issue. Looks like the query plan changed after the schema update.

        ________________________________
        From: Carol Davis <carol@example.com>
        Sent: Monday, March 10, 2025 5:00 PM
        To: support@example.com
        Cc: dba-team@example.com
        Subject: Database timeout on reporting queries

        Reports are timing out since this afternoon. The slow_query_log
        shows full table scans on the transactions table.
    """)
    path = tmp_path / "threaded.eml"
    path.write_text(eml_content, encoding="utf-8")
    return path


@pytest.fixture(scope="session")
def embedding_engine():
    """Session-scoped real EmbeddingEngine (loaded once for all tests)."""
    from email_issue_indexer.embeddings import EmbeddingEngine

    return EmbeddingEngine("all-MiniLM-L6-v2")
