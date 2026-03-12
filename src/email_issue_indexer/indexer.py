"""Orchestrate: parse EML files -> markdown -> embed -> store."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from .embeddings import EmbeddingEngine
from .markdown import to_markdown
from .parser import ParsedEmail, parse_eml
from .store import Store


def _chunked(iterable, size):
    """Yield successive chunks of the given size."""
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def _sanitize_filename(subject: str, date: str, max_len: int = 120) -> str:
    """Create a clean filename from subject and date.

    Returns something like: 2025-08-27_sync-failure-after-folder-move.md
    """
    # Extract date prefix (YYYY-MM-DD)
    date_prefix = ""
    date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', date)
    if not date_match:
        # Try to parse common date formats like "Wed, 27 Aug 2025"
        import email.utils
        try:
            parsed = email.utils.parsedate_to_datetime(date)
            date_prefix = parsed.strftime("%Y-%m-%d")
        except Exception:
            date_prefix = "unknown-date"
    else:
        date_prefix = date_match.group(0)

    # Clean subject: strip Re:/Fwd:, tags like [21v], lowercase, replace non-alnum with hyphens
    clean = subject.strip()
    clean = re.sub(r'^(?:Re|Fwd|Fw)\s*:\s*', '', clean, flags=re.IGNORECASE)
    # Keep tag content but remove brackets: [21v] -> 21v
    clean = re.sub(r'\[([^\]]*)\]', r'\1', clean)
    clean = clean.lower()
    clean = re.sub(r'[^a-z0-9]+', '-', clean)
    clean = clean.strip('-')

    # Truncate
    if len(clean) > max_len:
        clean = clean[:max_len].rsplit('-', 1)[0]

    return f"{date_prefix}_{clean}.md"


def _write_markdown(md: str, md_dir: Path, filename: str):
    """Write markdown to file, handling name collisions."""
    md_dir.mkdir(parents=True, exist_ok=True)
    path = md_dir / filename

    # Handle collisions by appending a number
    if path.exists():
        stem = path.stem
        suffix = path.suffix
        counter = 2
        while path.exists():
            path = md_dir / f"{stem}_{counter}{suffix}"
            counter += 1

    path.write_text(md, encoding="utf-8")


def index_directory(
    eml_dir: Path,
    store: Store,
    engine: EmbeddingEngine,
    md_dir: Path | None = None,
    batch_size: int = 100,
    verbose: bool = True,
) -> dict:
    """Index all EML files in a directory. Returns stats dict."""
    expert_emails = store.get_expert_emails()

    # Collect all EML files
    eml_files = sorted(eml_dir.rglob("*.eml"))
    total = len(eml_files)

    if verbose:
        print(f"Found {total} EML files in {eml_dir}")

    # Get existing hashes for incremental processing
    existing_hashes = store.get_file_hashes()

    # Filter to new/changed files
    to_process = []
    for f in eml_files:
        from .parser import hash_file
        h = hash_file(f)
        if existing_hashes.get(str(f)) != h:
            to_process.append((f, h))

    skipped = total - len(to_process)
    if verbose:
        print(f"Skipping {skipped} unchanged files, processing {len(to_process)}")

    if not to_process:
        return {"total": total, "processed": 0, "skipped": skipped, "errors": 0}

    errors = 0
    processed = 0

    for batch_num, batch in enumerate(_chunked(to_process, batch_size)):
        # Parse all EMLs in this batch
        parsed_list: list[tuple[ParsedEmail, str]] = []
        for filepath, filehash in batch:
            try:
                parsed = parse_eml(filepath)
                parsed_list.append((parsed, filehash))
            except Exception as e:
                errors += 1
                if verbose:
                    print(f"  ERROR parsing {filepath.name}: {e}", file=sys.stderr)

        if not parsed_list:
            continue

        # Collect all message texts for batch embedding
        all_texts = []
        text_map = []  # (parsed_idx, msg_idx)
        for i, (p, _) in enumerate(parsed_list):
            for j, msg in enumerate(p.messages):
                # Prepend subject for context
                text = f"{p.subject}\n\n{msg.body}" if p.subject else msg.body
                # Truncate very long texts (model max is ~512 tokens)
                all_texts.append(text[:2000])
                text_map.append((i, j))

        # Generate embeddings
        if all_texts:
            embeddings = engine.embed_batch(all_texts, show_progress=False)
        else:
            embeddings = []

        # Store everything
        for i, (parsed, filehash) in enumerate(parsed_list):
            md = to_markdown(parsed, expert_emails)
            email_id = store.upsert_email(parsed, md)

            # Write markdown file
            if md_dir:
                filename = _sanitize_filename(parsed.subject, parsed.date)
                _write_markdown(md, md_dir, filename)

            # Gather this email's embeddings
            msg_embeddings = []
            for k, (pi, mi) in enumerate(text_map):
                if pi == i:
                    msg_embeddings.append(embeddings[k])

            store.upsert_messages(email_id, parsed.messages, msg_embeddings, expert_emails)
            processed += 1

        store.commit()

        if verbose:
            done = min((batch_num + 1) * batch_size, len(to_process))
            print(f"  Indexed {done}/{len(to_process)} emails...")

    if verbose:
        print(f"Done! Processed {processed}, skipped {skipped}, errors {errors}")
        if md_dir:
            print(f"Markdown files written to {md_dir}")

    return {"total": total, "processed": processed, "skipped": skipped, "errors": errors}
