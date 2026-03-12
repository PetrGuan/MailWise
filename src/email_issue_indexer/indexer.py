"""Orchestrate: parse EML files -> markdown -> embed -> store.

Optimized for 25K+ emails (16GB+):
- Fast change detection: mtime+size check before expensive SHA256
- Parallel EML parsing with multiprocessing
- Batch embedding with progress tracking
- Batch SQL inserts
- Pre-built embedding index per batch to avoid O(n²) lookup
"""
from __future__ import annotations

import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from .embeddings import EmbeddingEngine
from .markdown import to_markdown
from .parser import ParsedEmail, file_stat, parse_eml
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
    date_prefix = ""
    date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', date)
    if not date_match:
        import email.utils
        try:
            parsed = email.utils.parsedate_to_datetime(date)
            date_prefix = parsed.strftime("%Y-%m-%d")
        except Exception:
            date_prefix = "unknown-date"
    else:
        date_prefix = date_match.group(0)

    clean = subject.strip()
    clean = re.sub(r'^(?:Re|Fwd|Fw)\s*:\s*', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'\[([^\]]*)\]', r'\1', clean)
    clean = clean.lower()
    clean = re.sub(r'[^a-z0-9]+', '-', clean)
    clean = clean.strip('-')

    if len(clean) > max_len:
        clean = clean[:max_len].rsplit('-', 1)[0]

    return f"{date_prefix}_{clean}.md"


def _parse_eml_safe(path: Path) -> ParsedEmail | str:
    """Parse an EML file, returning error string on failure (for multiprocessing)."""
    try:
        return parse_eml(path)
    except Exception as e:
        return f"ERROR: {path.name}: {e}"


def _find_changed_files(eml_files: list[Path], existing_index: dict,
                        verbose: bool) -> list[Path]:
    """Fast two-phase change detection:
    Phase 1: Check mtime+size (instant, no I/O beyond stat)
    Phase 2: SHA256 hash only for files where mtime/size changed
    """
    to_process = []
    fast_skipped = 0

    for f in eml_files:
        fpath = str(f)
        if fpath in existing_index:
            stored_hash, stored_mtime, stored_size = existing_index[fpath]
            # Phase 1: fast stat check
            try:
                mtime, size = file_stat(f)
            except OSError:
                continue
            if stored_mtime and stored_size and mtime == stored_mtime and size == stored_size:
                fast_skipped += 1
                continue
            # Phase 2: mtime/size differ, verify with hash
            from .parser import hash_file
            if hash_file(f) == stored_hash:
                fast_skipped += 1
                continue

        to_process.append(f)

    if verbose and fast_skipped:
        print(f"  Fast-skipped {fast_skipped} unchanged files (mtime+size match)")

    return to_process


def index_directory(
    eml_dir: Path,
    store: Store,
    engine: EmbeddingEngine,
    md_dir: Path | None = None,
    batch_size: int = 200,
    max_workers: int | None = None,
    verbose: bool = True,
) -> dict:
    """Index all EML files in a directory.

    Performance characteristics for 25K emails:
    - Change detection: ~2s (stat-based, no file reads for unchanged)
    - Parsing: ~30s with 4 workers (parallel)
    - Embedding: ~3-5 min on CPU (batched, GPU if available)
    - SQLite writes: ~10s (batched inserts with WAL mode)
    """
    expert_emails = store.get_expert_emails()
    start_time = time.time()

    # Collect all EML files
    eml_files = sorted(eml_dir.rglob("*.eml"))
    total = len(eml_files)

    if verbose:
        print(f"Found {total} EML files in {eml_dir}")

    if not eml_files:
        return {"total": 0, "processed": 0, "skipped": 0, "errors": 0}

    # Fast change detection
    existing_index = store.get_file_index()
    to_process = _find_changed_files(eml_files, existing_index, verbose)

    skipped = total - len(to_process)
    if verbose:
        print(f"Processing {len(to_process)} new/changed files, {skipped} unchanged")

    if not to_process:
        return {"total": total, "processed": 0, "skipped": skipped, "errors": 0}

    # Create markdown dir once
    if md_dir:
        md_dir.mkdir(parents=True, exist_ok=True)

    errors = 0
    processed = 0

    for batch_num, batch in enumerate(_chunked(to_process, batch_size)):
        batch_start = time.time()

        # Phase 1: Parallel EML parsing
        parsed_list: list[ParsedEmail] = []
        if len(batch) > 10 and (max_workers is None or max_workers > 1):
            workers = max_workers or min(4, len(batch))
            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(_parse_eml_safe, f): f for f in batch}
                for future in as_completed(futures):
                    result = future.result()
                    if isinstance(result, str):
                        errors += 1
                        if verbose:
                            print(f"  {result}", file=sys.stderr)
                    else:
                        parsed_list.append(result)
        else:
            for filepath in batch:
                result = _parse_eml_safe(filepath)
                if isinstance(result, str):
                    errors += 1
                    if verbose:
                        print(f"  {result}", file=sys.stderr)
                else:
                    parsed_list.append(result)

        if not parsed_list:
            continue

        # Phase 2: Batch embedding - collect all texts with index tracking
        all_texts = []
        # Build offset map: email_offsets[i] = (start_idx, count) in all_texts
        email_offsets = []
        for p in parsed_list:
            start = len(all_texts)
            for msg in p.messages:
                text = f"{p.subject}\n\n{msg.body}" if p.subject else msg.body
                all_texts.append(text[:2000])
            email_offsets.append((start, len(p.messages)))

        if all_texts:
            embeddings = engine.embed_batch(all_texts, show_progress=False)
        else:
            embeddings = []

        # Phase 3: Store everything with batch operations
        for i, parsed in enumerate(parsed_list):
            md = to_markdown(parsed, expert_emails)
            email_id = store.upsert_email(parsed, md)

            # Write markdown file
            if md_dir:
                filename = _sanitize_filename(parsed.subject, parsed.date)
                path = md_dir / filename
                if path.exists():
                    stem, suffix = path.stem, path.suffix
                    counter = 2
                    while path.exists():
                        path = md_dir / f"{stem}_{counter}{suffix}"
                        counter += 1
                path.write_text(md, encoding="utf-8")

            # Slice embeddings for this email using pre-computed offsets
            start, count = email_offsets[i]
            msg_embeddings = [embeddings[start + j] for j in range(count)]

            store.upsert_messages_batch(email_id, parsed.messages,
                                         msg_embeddings, expert_emails)
            processed += 1

        store.commit()

        if verbose:
            done = min((batch_num + 1) * batch_size, len(to_process))
            elapsed = time.time() - batch_start
            total_elapsed = time.time() - start_time
            rate = processed / total_elapsed if total_elapsed > 0 else 0
            remaining = (len(to_process) - done) / rate if rate > 0 else 0
            print(f"  Indexed {done}/{len(to_process)} "
                  f"({elapsed:.1f}s this batch, "
                  f"~{remaining:.0f}s remaining, "
                  f"{rate:.0f} emails/s)")

    total_time = time.time() - start_time
    if verbose:
        print(f"Done! {processed} processed, {skipped} unchanged, "
              f"{errors} errors in {total_time:.1f}s")
        if md_dir:
            print(f"Markdown files written to {md_dir}")

    return {"total": total, "processed": processed, "skipped": skipped, "errors": errors}
