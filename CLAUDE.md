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
├── store.py        # SQLite schema, CRUD, embedding storage
├── indexer.py      # Batch orchestrator: parse → embed → store → write markdown
├── search.py       # Semantic search with expert score boosting
└── rag.py          # RAG layer: retrieval + Claude Code CLI invocation
```

## Key commands

```bash
./mailwise index          # Index EML files
./mailwise search "..."   # Semantic search
./mailwise analyze "..."  # RAG analysis via Claude
./mailwise stats          # Index statistics
./mailwise experts list   # Show configured experts
```

## Development

```bash
pip install -e .
cp config.example.yaml config.yaml  # Then edit with your settings
```

## Architecture notes

- **Incremental indexing**: Files are tracked by SHA256 hash; unchanged files are skipped on re-index
- **Thread splitting**: Regex-based splitting on `From:/Sent:` patterns (Outlook inline reply format)
- **Expert boosting**: Messages from configured expert emails get a configurable score multiplier in search results
- **RAG invocation**: Uses `claude --print` subprocess with `CLAUDECODE` env var unset to allow nested invocation
- **Embeddings**: Each individual reply in a thread is embedded separately (not the whole email), prefixed with the subject for context. Truncated to 2000 chars.

## CRITICAL: Data privacy rules

**This is an open source project. The following rules are non-negotiable:**

1. **NEVER commit real email addresses** — not in source code, comments, tests, docs, or examples. Use placeholders like `engineer@company.com` or `jane.doe@example.com`.

2. **NEVER commit real names of people** — not in source code, comments, tests, docs, or examples. Use generic names like "Jane Doe" or "Senior Engineer".

3. **NEVER commit real email content, thread subjects, or issue descriptions** from any user's data. Use generic examples like "sync failure after migration".

4. **NEVER commit file paths** that reveal usernames, company names, or internal project names. Use relative paths or `/path/to/...` placeholders.

5. **NEVER commit config.yaml** — it contains real expert emails and local paths. Only `config.example.yaml` (with placeholders) is committed.

6. **The `data/`, `markdown/`, and `*.eml` paths are gitignored.** Never modify `.gitignore` to un-ignore these.

7. **Before any commit**, mentally verify: "Could someone reading this diff identify a real person, company team, or internal system?" If yes, redact it.

8. **Test data**: If tests need sample EML files, create synthetic ones with fake data. Never copy real emails into the repo.

## Code conventions

- Use `from __future__ import annotations` in all modules (Python 3.9 compat)
- Keep dependencies minimal — prefer stdlib where possible
- SQLite for storage, no external databases
- CLI uses Click with `@click.pass_context` for config propagation
