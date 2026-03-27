# Contributing to MailWise

Thanks for your interest in contributing!

## Getting started

1. Fork the repo and clone it
2. Install in development mode with test dependencies: `pip install -e ".[dev]"`
3. Set up config: `mailwise init` or `cp config.example.yaml config.yaml`
4. Install the pre-commit hook: `./scripts/install-hooks.sh`
5. Make your changes

## Running tests

```bash
pytest                          # run all tests
pytest tests/test_parser.py -v  # run a specific test file
pytest --cov=email_issue_indexer --cov-report=term-missing  # with coverage
```

Tests use synthetic EML data — no real emails needed.

## Guidelines

- Keep it simple — avoid over-engineering
- Add tests for new features
- Don't commit any real email data or employee information
- `config.yaml` is gitignored for a reason — never hardcode paths or email addresses in source code
- Use `from __future__ import annotations` in all modules

## Reporting issues

Open an issue on GitHub. If it involves parsing edge cases, include a sanitized/anonymized sample EML if possible.
