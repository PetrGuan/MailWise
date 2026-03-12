# MailWise

Turn email threads into a searchable knowledge base. Parse EML files, index with embeddings, and use RAG to learn how your best engineers analyze issues.

## What it does

MailWise reads `.eml` files (exported from Outlook, Thunderbird, etc.), splits email threads into individual replies, and builds a semantic search index. You can then:

- **Search** for similar past issues using natural language
- **Analyze** new issues with RAG — Claude reads how your experts solved similar problems and synthesizes advice
- **Tag expert engineers** whose replies get boosted in search results and highlighted in output

## Why

If your team handles bugs/incidents via email, years of tribal knowledge is buried in threads. MailWise makes that knowledge searchable and actionable.

## Quick start

### Prerequisites

- Python 3.10+
- [Claude Code](https://claude.ai/code) (for the `analyze` command — uses your existing auth, no API key needed)

### Install

```bash
git clone https://github.com/peterxcli/MailWise.git
cd MailWise
pip install -e .
```

### Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your settings:

```yaml
eml_directory: /path/to/your/eml/files
database: data/index.db
markdown_directory: markdown
embedding_model: all-MiniLM-L6-v2
expert_boost: 1.5

experts:
  - email: senior.dev@company.com
    name: Jane Doe
```

### Usage

```bash
# Index your emails (incremental — only processes new/changed files)
mailwise index

# Search for similar past issues
mailwise search "sync failure after folder migration"

# Search with previews
mailwise search "calendar not updating" --show-body

# Only show expert replies
mailwise search "deleted emails reappear" --expert-only

# Deep analysis — Claude reasons over similar expert threads
mailwise analyze "User reports emails moved to local folder keep reappearing in Inbox"

# View full markdown of a specific email thread
mailwise show 42

# Check index stats
mailwise stats
```

### Managing experts

```bash
# Add an expert
mailwise experts add engineer@company.com --name "Jane Doe"

# List all experts
mailwise experts list

# Remove an expert
mailwise experts remove engineer@company.com
```

## How it works

```
EML files → Parser → Markdown + Embeddings → SQLite index
                                                    ↓
                              Query → Semantic search → Top matches
                                                            ↓
                                          Claude (via RAG) → Expert-informed analysis
```

1. **Parse**: EML files are parsed and email threads are split into individual replies using Outlook-style `From:/Sent:` delimiters
2. **Clean**: Microsoft SafeLinks are unwrapped, mailto artifacts are removed
3. **Markdown**: Each thread becomes a structured markdown file with `[Expert]` tags on replies from your designated engineers
4. **Embed**: Each reply is embedded using `all-MiniLM-L6-v2` (runs locally, no API calls)
5. **Index**: Embeddings and metadata are stored in SQLite for fast retrieval
6. **Search**: Cosine similarity with expert score boosting finds relevant past issues
7. **Analyze**: Top matches are fed to Claude (via Claude Code CLI) with a system prompt that focuses on expert reasoning patterns

## Architecture

```
src/email_issue_indexer/
├── cli.py          # Click-based CLI
├── parser.py       # EML parsing + thread splitting
├── markdown.py     # Markdown conversion with expert tags
├── safelinks.py    # Microsoft SafeLinks URL cleaning
├── embeddings.py   # sentence-transformers embeddings + vector search
├── store.py        # SQLite storage layer
├── indexer.py      # Orchestrator with incremental processing
├── search.py       # Similarity search with expert boosting
└── rag.py          # RAG layer using Claude Code CLI
```

## Privacy

All processing is local:
- Embeddings run on your machine (no data sent to any API for indexing)
- Email content stays in your local SQLite database and markdown files
- The `analyze` command sends relevant thread excerpts to Claude — same as chatting in Claude Code

Your `config.yaml`, `data/`, and `markdown/` directories are gitignored by default. Only `config.example.yaml` (with no real data) is committed.

## License

MIT
