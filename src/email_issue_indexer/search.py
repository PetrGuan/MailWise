"""Search for similar issues using embeddings.

Optimized: loads embedding vectors as a contiguous numpy array directly
from SQLite, avoiding the overhead of constructing 100K+ Python objects.
Only fetches full metadata for the top-k results.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from .embeddings import EmbeddingEngine
from .store import Store, StoredEmail, StoredMessage


@dataclass
class SearchResult:
    message: StoredMessage
    email: StoredEmail
    score: float


def find_similar(
    query: str,
    store: Store,
    engine: EmbeddingEngine,
    top_k: int = 10,
    expert_boost: float = 1.5,
    expert_only: bool = False,
) -> list[SearchResult]:
    """Find thread messages most similar to the query.

    Optimized path:
    1. Load only (id, email_id, is_expert, embedding_blob) — no text/metadata
    2. Build numpy matrix directly from blobs
    3. Single matrix multiply for cosine similarity
    4. Only fetch full metadata for the top-k winners
    """
    corpus, expert_mask, msg_ids, email_ids, is_expert_list = store.get_search_vectors()

    if len(corpus) == 0:
        return []

    if expert_only:
        mask = expert_mask
        corpus = corpus[mask]
        msg_ids = [m for m, e in zip(msg_ids, is_expert_list) if e]
        email_ids = [e for e, ex in zip(email_ids, is_expert_list) if ex]
        expert_mask = np.ones(len(corpus), dtype=bool)
        if len(corpus) == 0:
            return []

    # Embed query
    query_vec = engine.embed(query)

    # Search
    results = EmbeddingEngine.search(
        query_vec, corpus, expert_mask, expert_boost, top_k * 3  # over-fetch for dedup
    )

    # Deduplicate by normalized subject (same thread = same issue)
    search_results = []
    seen_subjects = set()
    for idx, score in results:
        eid = email_ids[idx]

        msg = store.get_message_metadata(msg_ids[idx])
        email_record = store.get_email(eid)
        if not msg or not email_record:
            continue

        # Normalize subject: strip Re:/Fwd:, lowercase, collapse whitespace
        norm = re.sub(r'^(?:Re|Fwd|Fw)\s*:\s*', '', email_record.subject,
                      flags=re.IGNORECASE).strip().lower()
        norm = re.sub(r'\s+', ' ', norm)
        if norm in seen_subjects:
            continue
        seen_subjects.add(norm)

        search_results.append(SearchResult(
            message=msg, email=email_record, score=score
        ))

        if len(search_results) >= top_k:
            break

    return search_results


def format_results(results: list[SearchResult], show_body: bool = False) -> str:
    """Format search results for display."""
    if not results:
        return "No similar issues found."

    lines = []
    for i, r in enumerate(results, 1):
        expert_tag = " [Expert]" if r.message.is_expert else ""
        lines.append(f"{i}. [{r.score:.3f}] {r.email.subject}")
        lines.append(f"   By: {r.message.from_name or r.message.from_addr}{expert_tag}")
        lines.append(f"   Date: {r.message.sent_date or r.email.date}")
        lines.append(f"   Email ID: {r.email.id}")

        if show_body:
            preview = r.message.body_text[:300].replace("\n", "\n   ")
            lines.append(f"   Preview: {preview}")

        lines.append("")

    return "\n".join(lines)
