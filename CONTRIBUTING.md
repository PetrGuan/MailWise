# Contributing to MailWise

Thanks for your interest in contributing!

## Getting started

1. Fork the repo and clone it
2. Install in development mode: `pip install -e .`
3. Copy config: `cp config.example.yaml config.yaml`
4. Make your changes

## Guidelines

- Keep it simple — avoid over-engineering
- Test with real EML files when possible
- Don't commit any real email data or employee information
- `config.yaml` is gitignored for a reason — never hardcode paths or email addresses in source code

## Reporting issues

Open an issue on GitHub. If it involves parsing edge cases, include a sanitized/anonymized sample EML if possible.
