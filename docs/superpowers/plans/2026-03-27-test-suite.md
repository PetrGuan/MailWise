# Test Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add pytest-based tests covering parser, safelinks, markdown, store, embeddings, search, and a lightweight integration test.

**Architecture:** Each module gets its own test file. Shared fixtures in `conftest.py` provide synthetic EML files and temp databases. Real embedding engine is session-scoped (loaded once). All test data is synthetic.

**Tech Stack:** pytest, pytest-cov, numpy, sentence-transformers (already installed)

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `pyproject.toml` | Add pytest/pytest-cov dev dependencies, pytest config |
| Create | `tests/__init__.py` | Package marker |
| Create | `tests/conftest.py` | Shared fixtures: tmp_store, sample EMLs, embedding_engine |
| Create | `tests/test_safelinks.py` | SafeLinks URL cleaning tests |
| Create | `tests/test_parser.py` | EML parsing and thread splitting tests |
| Create | `tests/test_markdown.py` | Markdown conversion and expert tagging tests |
| Create | `tests/test_store.py` | SQLite CRUD and vector storage tests |
| Create | `tests/test_embeddings.py` | Embedding generation and vector search tests |
| Create | `tests/test_search.py` | End-to-end search with dedup and formatting tests |
| Create | `tests/test_integration.py` | Index-then-search pipeline test |

---

### Task 1: Add pytest dependencies and config

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dev dependencies and pytest config to pyproject.toml**

Add after the `[project.urls]` section:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Install dev dependencies**

Run: `pip install -e ".[dev]"`
Expected: pytest and pytest-cov installed successfully

- [ ] **Step 3: Create tests package**

Create empty `tests/__init__.py`.

- [ ] **Step 4: Verify pytest runs**

Run: `cd /Users/petr/Documents/GitHub/MailWise && python -m pytest --co -q`
Expected: "no tests ran" (no test files yet, but no errors)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/__init__.py
git commit -m "chore: add pytest dev dependencies and test config"
```

---

### Task 2: Create shared fixtures (conftest.py)

**Files:**
- Create: `tests/conftest.py`

- [ ] **Step 1: Write conftest.py with all shared fixtures**

```python
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
```

- [ ] **Step 2: Verify fixtures load**

Run: `cd /Users/petr/Documents/GitHub/MailWise && python -m pytest --co -q`
Expected: No errors, no tests collected yet

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add shared fixtures with synthetic EML data"
```

---

### Task 3: Test safelinks module

**Files:**
- Create: `tests/test_safelinks.py`

- [ ] **Step 1: Write safelinks tests**

```python
"""Tests for Microsoft SafeLinks URL cleaning."""
from __future__ import annotations

from email_issue_indexer.safelinks import clean_safelink, clean_text


class TestCleanSafelink:
    def test_extracts_original_url(self):
        safelink = (
            "https://nam06.safelinks.protection.outlook.com/"
            "?url=https%3A%2F%2Fexample.com%2Fpage%3Fid%3D42"
            "&data=05&sdata=abc&reserved=0"
        )
        assert clean_safelink(safelink) == "https://example.com/page?id=42"

    def test_returns_non_safelink_unchanged(self):
        url = "https://example.com/normal-page"
        assert clean_safelink(url) == url

    def test_returns_malformed_safelink_unchanged(self):
        url = "https://safelinks.protection.outlook.com/?nourl=1"
        assert clean_safelink(url) == url


class TestCleanText:
    def test_replaces_safelinks_in_text(self):
        text = (
            "Check this link: "
            "https://nam06.safelinks.protection.outlook.com/"
            "?url=https%3A%2F%2Fexample.com%2Fhelp"
            "&data=05 for details."
        )
        result = clean_text(text)
        assert "https://example.com/help" in result
        assert "safelinks" not in result

    def test_cleans_mailto_artifacts(self):
        text = "Contact <mailto:jane@example.com> for help."
        result = clean_text(text)
        assert result == "Contact (jane@example.com) for help."

    def test_handles_plain_text_unchanged(self):
        text = "No links here, just plain text."
        assert clean_text(text) == text
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/petr/Documents/GitHub/MailWise && python -m pytest tests/test_safelinks.py -v`
Expected: All 6 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_safelinks.py
git commit -m "test: add safelinks URL cleaning tests"
```

---

### Task 4: Test parser module

**Files:**
- Create: `tests/test_parser.py`

- [ ] **Step 1: Write parser tests**

```python
"""Tests for EML parsing and thread splitting."""
from __future__ import annotations

from pathlib import Path

from email_issue_indexer.parser import (
    _extract_addr,
    _extract_addr_list,
    _split_thread,
    file_stat,
    hash_file,
    parse_eml,
)


class TestExtractAddr:
    def test_name_and_email(self):
        name, addr = _extract_addr("Jane Doe <jane@example.com>")
        assert name == "Jane Doe"
        assert addr == "jane@example.com"

    def test_quoted_name(self):
        name, addr = _extract_addr('"Jane Doe" <jane@example.com>')
        assert name == "Jane Doe"
        assert addr == "jane@example.com"

    def test_bare_email(self):
        name, addr = _extract_addr("jane@example.com")
        assert name == ""
        assert addr == "jane@example.com"

    def test_none_input(self):
        name, addr = _extract_addr(None)
        assert name == ""
        assert addr == ""

    def test_mailto_artifact_cleaned(self):
        name, addr = _extract_addr("jane@example.com(jane@example.com)")
        assert addr == "jane@example.com"


class TestExtractAddrList:
    def test_multiple_addresses(self):
        addrs = _extract_addr_list("alice@example.com, bob@example.com")
        assert addrs == ["alice@example.com", "bob@example.com"]

    def test_empty_input(self):
        assert _extract_addr_list(None) == []
        assert _extract_addr_list("") == []


class TestSplitThread:
    def test_single_message(self):
        messages = _split_thread("Just a simple body with no thread headers.")
        assert len(messages) == 1
        assert messages[0].position == 0
        assert "simple body" in messages[0].body

    def test_outlook_thread(self):
        text = (
            "Top reply content here.\n\n"
            "________________________________\n"
            "From: Bob Chen <bob@example.com>\n"
            "Sent: Tuesday, March 11, 2025 8:30 AM\n"
            "To: support@example.com\n"
            "Subject: RE: Some issue\n"
            "\n"
            "Bob's earlier message.\n"
        )
        messages = _split_thread(text)
        assert len(messages) == 2
        assert "Top reply" in messages[0].body
        assert messages[1].from_addr == "bob@example.com"
        assert "Bob's earlier" in messages[1].body

    def test_empty_text(self):
        messages = _split_thread("")
        assert messages == []


class TestFileStat:
    def test_returns_mtime_and_size(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        mtime, size = file_stat(f)
        assert isinstance(mtime, float)
        assert size == 5


class TestHashFile:
    def test_consistent_hash(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        h1 = hash_file(f)
        h2 = hash_file(f)
        assert h1 == h2
        assert len(h1) == 64  # SHA256 hex digest


class TestParseEml:
    def test_simple_eml(self, sample_eml_path):
        result = parse_eml(sample_eml_path)
        assert result.subject == "Sync failure after migration"
        assert result.from_addr == "jane.doe@example.com"
        assert result.from_name == "Jane Doe"
        assert "support@example.com" in result.to_addrs
        assert result.message_id == "<msg001@example.com>"
        assert len(result.messages) >= 1
        assert "0x800CCC0E" in result.messages[0].body

    def test_threaded_eml(self, threaded_eml_path):
        result = parse_eml(threaded_eml_path)
        assert result.subject == "RE: Database timeout on reporting queries"
        assert result.in_reply_to == "<msg001@example.com>"
        # Should have 3 messages: top reply + 2 thread splits
        assert len(result.messages) == 3
        # First message (top reply) should be from the EML header sender
        assert result.messages[0].from_addr == "alice@example.com"
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/petr/Documents/GitHub/MailWise && python -m pytest tests/test_parser.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_parser.py
git commit -m "test: add EML parsing and thread splitting tests"
```

---

### Task 5: Test markdown module

**Files:**
- Create: `tests/test_markdown.py`

- [ ] **Step 1: Write markdown tests**

```python
"""Tests for markdown conversion and expert tagging."""
from __future__ import annotations

from email_issue_indexer.markdown import to_markdown
from email_issue_indexer.parser import parse_eml


class TestToMarkdown:
    def test_contains_subject_as_heading(self, sample_eml_path):
        parsed = parse_eml(sample_eml_path)
        md = to_markdown(parsed)
        assert "# Sync failure after migration" in md

    def test_contains_participants(self, sample_eml_path):
        parsed = parse_eml(sample_eml_path)
        md = to_markdown(parsed)
        assert "**Participants:**" in md
        assert "Jane Doe" in md

    def test_contains_reply_sections(self, threaded_eml_path):
        parsed = parse_eml(threaded_eml_path)
        md = to_markdown(parsed)
        assert "## Reply 1" in md
        assert "## Reply 2" in md
        assert "## Reply 3" in md

    def test_expert_tagging(self, threaded_eml_path):
        parsed = parse_eml(threaded_eml_path)
        expert_emails = {"bob@example.com"}
        md = to_markdown(parsed, expert_emails)
        assert "**[Expert]**" in md
        # Only Bob should be tagged, not others
        assert md.count("**[Expert]**") == 1

    def test_no_experts_no_tags(self, threaded_eml_path):
        parsed = parse_eml(threaded_eml_path)
        md = to_markdown(parsed, expert_emails=set())
        assert "[Expert]" not in md
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/petr/Documents/GitHub/MailWise && python -m pytest tests/test_markdown.py -v`
Expected: All 5 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_markdown.py
git commit -m "test: add markdown conversion and expert tagging tests"
```

---

### Task 6: Test store module

**Files:**
- Create: `tests/test_store.py`

- [ ] **Step 1: Write store tests**

```python
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
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/petr/Documents/GitHub/MailWise && python -m pytest tests/test_store.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_store.py
git commit -m "test: add SQLite store CRUD and vector storage tests"
```

---

### Task 7: Test embeddings module

**Files:**
- Create: `tests/test_embeddings.py`

- [ ] **Step 1: Write embeddings tests**

```python
"""Tests for embedding generation and vector search."""
from __future__ import annotations

import numpy as np

from email_issue_indexer.embeddings import EmbeddingEngine


class TestEmbed:
    def test_returns_normalized_vector(self, embedding_engine):
        vec = embedding_engine.embed("test query about database errors")
        assert vec.ndim == 1
        assert vec.shape[0] > 0
        # Normalized vectors have L2 norm ≈ 1.0
        assert abs(np.linalg.norm(vec) - 1.0) < 0.01

    def test_similar_texts_have_high_similarity(self, embedding_engine):
        v1 = embedding_engine.embed("database connection timeout")
        v2 = embedding_engine.embed("database connection error")
        v3 = embedding_engine.embed("recipe for chocolate cake")
        # Similar texts should score higher than unrelated
        sim_related = float(v1 @ v2)
        sim_unrelated = float(v1 @ v3)
        assert sim_related > sim_unrelated


class TestEmbedBatch:
    def test_returns_correct_shape(self, embedding_engine):
        texts = ["first text", "second text", "third text"]
        result = embedding_engine.embed_batch(texts, show_progress=False)
        assert result.shape[0] == 3
        assert result.shape[1] > 0

    def test_empty_list(self, embedding_engine):
        result = embedding_engine.embed_batch([], show_progress=False)
        assert len(result) == 0


class TestSearch:
    def test_ranking_order(self):
        """Search should return highest similarity first."""
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        corpus = np.array([
            [0.1, 0.9, 0.0],   # low similarity
            [0.9, 0.1, 0.0],   # high similarity
            [0.5, 0.5, 0.0],   # medium similarity
        ], dtype=np.float32)
        # Normalize
        corpus = corpus / np.linalg.norm(corpus, axis=1, keepdims=True)

        results = EmbeddingEngine.search(query, corpus, top_k=3)
        indices = [idx for idx, _ in results]
        assert indices[0] == 1  # highest similarity first

    def test_expert_boost(self):
        """Expert boost should increase scores for expert messages."""
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        corpus = np.array([
            [0.8, 0.2, 0.0],   # non-expert, high base similarity
            [0.5, 0.5, 0.0],   # expert, medium base similarity
        ], dtype=np.float32)
        corpus = corpus / np.linalg.norm(corpus, axis=1, keepdims=True)
        expert_mask = np.array([False, True])

        results = EmbeddingEngine.search(
            query, corpus, expert_mask=expert_mask, expert_boost=2.0, top_k=2
        )
        # With 2x boost, the expert (idx 1) should rank first
        assert results[0][0] == 1

    def test_top_k_limits_output(self):
        query = np.array([1.0, 0.0], dtype=np.float32)
        corpus = np.random.randn(100, 2).astype(np.float32)
        corpus = corpus / np.linalg.norm(corpus, axis=1, keepdims=True)

        results = EmbeddingEngine.search(query, corpus, top_k=5)
        assert len(results) == 5
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/petr/Documents/GitHub/MailWise && python -m pytest tests/test_embeddings.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_embeddings.py
git commit -m "test: add embedding generation and vector search tests"
```

---

### Task 8: Test search module

**Files:**
- Create: `tests/test_search.py`

- [ ] **Step 1: Write search tests**

```python
"""Tests for semantic search with deduplication and formatting."""
from __future__ import annotations

import numpy as np

from email_issue_indexer.parser import ParsedEmail, ThreadMessage
from email_issue_indexer.search import find_similar, format_results
from email_issue_indexer.store import StoredEmail, StoredMessage, SearchResult


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
        from email_issue_indexer.markdown import to_markdown
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
        # Re-insert messages with expert flag
        corpus, _, msg_ids, email_ids, _ = tmp_store.get_search_vectors()
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
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/petr/Documents/GitHub/MailWise && python -m pytest tests/test_search.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_search.py
git commit -m "test: add semantic search and result formatting tests"
```

---

### Task 9: Integration test

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
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
        assert "timeout" in results[0].email.subject.lower() or \
               "database" in results[0].email.subject.lower()

        # Re-index should skip unchanged files
        result2 = index_directory(
            eml_dir, store, embedding_engine,
            md_dir=md_dir, batch_size=10, max_workers=1, verbose=False,
        )
        assert result2["processed"] == 0
        assert result2["skipped"] == 2

        store.close()
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/petr/Documents/GitHub/MailWise && python -m pytest tests/test_integration.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add index-then-search integration test"
```

---

### Task 10: Run full suite with coverage

- [ ] **Step 1: Run all tests with coverage**

Run: `cd /Users/petr/Documents/GitHub/MailWise && python -m pytest --cov=email_issue_indexer --cov-report=term-missing -v`
Expected: All tests PASS, coverage report shows ~70%+ for core modules

- [ ] **Step 2: Fix any failures**

If any test fails, fix it and re-run.

- [ ] **Step 3: Final commit**

```bash
git add -A tests/
git commit -m "test: complete core pipeline test suite with ~70% coverage"
```
