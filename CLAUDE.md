# CLAUDE.md - Project instructions for Claude Code

## Project overview

MailWise is an open source tool that converts EML email threads into a searchable knowledge base with RAG-powered analysis. It parses email threads, generates embeddings locally, and uses Claude to synthesize expert insights from similar past issues.

## Tech stack

- **Language**: Python 3.10+
- **CLI**: Click
- **Embeddings**: sentence-transformers (all-MiniLM-L6-v2, runs locally)
- **Storage**: SQLite (embeddings stored as BLOBs)
- **RAG**: Claude Code CLI (`claude --print`)
- **Config**: YAML

## Project structure

```
src/email_issue_indexer/
├── cli.py          # Click CLI entry point
├── parser.py       # EML parsing + Outlook thread splitting
├── markdown.py     # Thread → markdown conversion with [Expert] tags
├── safelinks.py    # Microsoft SafeLinks URL unwrapping
├── embeddings.py   # sentence-transformers wrapper + cosine similarity search
├── store.py        # SQLite schema, CRUD, embedding storage (performance-tuned)
├── indexer.py      # Parallel batch orchestrator: parse → embed → store → write markdown
├── search.py       # Semantic search with expert score boosting (optimized vector path)
└── rag.py          # RAG layer: retrieval + Claude Code CLI invocation
```

Key non-source files:
```
config.example.yaml  # Template config (committed)
config.yaml          # User config with real data (NEVER committed)
emails/              # EML input directory (gitignored)
data/                # SQLite database (gitignored)
markdown/            # Generated markdown output (gitignored)
scripts/pre-commit   # PII-scanning git hook
```

## Key commands

```bash
./mailwise index          # Index EML files (incremental, parallel)
./mailwise search "..."   # Semantic search
./mailwise analyze "..."  # RAG analysis via Claude
./mailwise stats          # Index statistics
./mailwise experts list   # Show configured experts
./mailwise experts add    # Add expert engineer
./mailwise show <id>      # View full markdown for an email
```

## Development

```bash
pip install -e .
cp config.example.yaml config.yaml  # Then edit with your settings
./scripts/install-hooks.sh           # Install PII-scanning pre-commit hook
```

## Architecture & performance notes

### Indexing pipeline (designed for 25K+ emails, 16GB+)

1. **Two-phase change detection**: `stat()` mtime+size check first (instant), SHA256 hash only when mtime/size differ. Incremental re-index of unchanged corpus takes ~2-3s for 25K files.

2. **Parallel EML parsing**: `ProcessPoolExecutor` with configurable workers (default 4). Each worker parses EML, splits threads, cleans SafeLinks independently.

3. **Batch embedding**: Texts collected per batch with pre-computed offset array for O(1) per-email slicing (avoids O(n²) text_map scan). Truncated to 2000 chars per message.

4. **Batch SQL writes**: `executemany` for thread_messages inserts. SQLite tuned with WAL journal, 64MB cache, 256MB mmap, NORMAL sync.

5. **Progress tracking**: Real-time ETA, emails/s rate, batch timing.

### Search path (optimized for 100K+ vectors)

- `store.get_search_vectors()` loads only `(id, email_id, is_expert, embedding_blob)` — no text or metadata deserialized for the full corpus
- Builds contiguous numpy array directly from BLOBs
- Single matrix multiply for cosine similarity across entire corpus
- Full metadata fetched only for top-k winners via `get_message_metadata()`
- Expert score boosting applied as a mask multiply

### Thread splitting

- Regex-based splitting on `From:/Sent:` patterns (Outlook inline reply format)
- Each individual reply embedded separately (not whole email), prefixed with subject for context
- Handles nested threads, missing To/Cc/Subject lines, underscore separators

### RAG invocation

- Uses `claude --print` subprocess with `CLAUDECODE`/`CLAUDE_CODE_ENTRYPOINT` env vars unset to allow nested invocation from within Claude Code sessions
- System prompt configurable via `config.yaml` `system_prompt` field
- Context window managed by `_build_context()` with 80K char limit

## CRITICAL: Data privacy rules

**This is an open source project. The following rules are non-negotiable:**

1. **NEVER commit real email addresses** — not in source code, comments, tests, docs, or examples. Use placeholders like `engineer@company.com` or `jane.doe@example.com`.

2. **NEVER commit real names of people** — not in source code, comments, tests, docs, or examples. Use generic names like "Jane Doe" or "Senior Engineer".

3. **NEVER commit real email content, thread subjects, or issue descriptions** from any user's data. Use generic examples like "sync failure after migration".

4. **NEVER commit file paths** that reveal usernames, company names, or internal project names. Use relative paths or `/path/to/...` placeholders.

5. **NEVER commit config.yaml** — it contains real expert emails and local paths. Only `config.example.yaml` (with placeholders) is committed.

6. **The `data/`, `markdown/`, `emails/`, and `*.eml` paths are gitignored.** Never modify `.gitignore` to un-ignore these.

7. **Before any commit**, mentally verify: "Could someone reading this diff identify a real person, company team, or internal system?" If yes, redact it.

8. **Test data**: If tests need sample EML files, create synthetic ones with fake data. Never copy real emails into the repo.

9. **Pre-commit hook**: A git hook in `scripts/pre-commit` scans staged diffs for company email patterns and blocks the commit. Always keep this active. Run `./scripts/install-hooks.sh` after cloning.

## Code conventions

- Use `from __future__ import annotations` in all modules (Python 3.9 compat)
- Keep dependencies minimal — prefer stdlib where possible
- SQLite for storage, no external databases
- CLI uses Click with `@click.pass_context` for config propagation
- Performance-critical paths: avoid constructing Python objects for bulk data; prefer numpy arrays and raw tuples from SQLite
- Batch operations: prefer `executemany` over loops of `execute`
- Parallel parsing: use `ProcessPoolExecutor`; `_parse_eml_safe` returns error strings instead of raising (for multiprocessing compatibility)
