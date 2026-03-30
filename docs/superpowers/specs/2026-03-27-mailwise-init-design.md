# `mailwise init` Design

## Goal

Add an interactive `mailwise init` command that creates a working configuration from scratch, reducing setup friction for new users.

## Flow

1. Check if `config.yaml` already exists — if so, ask to overwrite or abort
2. Prompt for EML directory path — validate it exists and contains `.eml` files, show count
3. Prompt for expert engineers (optional, repeating) — email + name, or skip
4. Create `data/` and `markdown/` directories
5. Write `config.yaml` with collected values + sensible defaults
6. Offer to run a quick test index (first 5 files) to verify the pipeline works
7. Print a "you're all set" summary with next steps

## Implementation

Added to `cli.py` as a new Click command in the existing CLI group. No new modules — uses existing `Store`, `EmbeddingEngine`, and `index_directory`.

## Config defaults written

```yaml
eml_directory: <user-provided>
database: data/index.db
markdown_directory: markdown
embedding_model: all-MiniLM-L6-v2
expert_boost: 1.5
experts:
  - email: <user-provided>
    name: <user-provided>
```

## Testing

Add a test using Click's `CliRunner` with input simulation to verify the happy path produces a valid `config.yaml` with correct content. Test both the "no experts" and "with experts" paths.

## Out of scope

- Dependency checking (happens naturally on first `mailwise index`)
- Pre-commit hook installation (developer concern)
- Config migration from older formats
