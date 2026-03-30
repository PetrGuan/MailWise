# Test Suite Design — Core Pipeline Coverage

## Goal

Add pytest-based tests covering parser, safelinks, markdown, store, embeddings, and search modules. Target ~70% coverage of the critical paths. All test data is synthetic — no real emails.

## Framework & Setup

- **pytest** + **pytest-cov** added as optional dev dependencies in `pyproject.toml`
- Shared fixtures in `tests/conftest.py`
- Real `EmbeddingEngine` for embedding/search tests (session-scoped, loaded once)
- Temporary directories and in-memory SQLite for isolation

## Fixtures (conftest.py)

| Fixture | Scope | Description |
|---------|-------|-------------|
| `tmp_store` | function | Fresh SQLite `Store` in a temp dir, closed after test |
| `sample_eml_path` | function | Writes a single-message synthetic EML to tmp dir |
| `threaded_eml_path` | function | Writes an Outlook-style threaded EML (From:/Sent: splits) |
| `embedding_engine` | session | Real `EmbeddingEngine("all-MiniLM-L6-v2")`, loaded once |

## Test Modules

### test_parser.py
- Parse single-message EML: subject, from, to, message_id, body extracted correctly
- Parse threaded EML: correct message count, positions, from_addrs, bodies
- `_extract_addr`: `"Name <email>"`, bare email, None input
- `_extract_addr_list`: multiple addresses, empty input
- `file_stat` and `hash_file`: basic sanity on a temp file

### test_safelinks.py
- `clean_safelink`: SafeLinks URL → original URL
- `clean_safelink`: non-SafeLinks URL returned as-is
- `clean_text`: mixed SafeLinks + mailto artifacts cleaned

### test_markdown.py
- `to_markdown`: output contains H1 subject, participants, reply sections
- Expert tagging: expert email gets `[Expert]` tag
- No expert emails configured: no tags

### test_store.py
- Schema creation on fresh DB
- `upsert_email` + `get_email` round-trip
- `upsert_messages_batch` + `get_message_metadata` round-trip
- `get_search_vectors`: correct numpy arrays and expert mask
- `get_file_index`: returns stored file metadata
- Expert CRUD: `add_expert`, `get_experts`, `remove_expert`, `get_expert_emails`
- `get_stats`: correct counts

### test_embeddings.py
- `embed` returns normalized vector (L2 norm ≈ 1.0)
- `embed_batch` returns shape (n, dim)
- `embed_batch([])` returns empty array
- `EmbeddingEngine.search`: ranking correct, expert boost applied, top_k honored

### test_search.py
- `find_similar` with 3 indexed synthetic emails returns ranked results
- `expert_only=True` filters to expert messages only
- Subject deduplication collapses same-thread results
- `format_results` produces expected text output

### test_integration.py
- Index 2 synthetic EMLs via `index_directory(max_workers=1)`
- Search the indexed data and verify results return
- Verify stats reflect indexed count

## Out of Scope (Phase B)
- CLI command tests (Click test runner)
- RAG layer tests (mocked Claude subprocess)
- Full multiprocessing integration tests
