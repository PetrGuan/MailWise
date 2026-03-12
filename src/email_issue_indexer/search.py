"""Search for similar issues using embeddings."""
from __future__ import annotations

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

    Args:
        query: Natural language description of the issue.
        store: Database store.
        engine: Embedding engine.
        top_k: Number of results to return.
        expert_boost: Multiplier for expert message scores.
        expert_only: If True, only return messages from experts.
    """
    # Load all messages with embeddings
    messages = store.get_all_messages_with_embeddings()
    if not messages:
        return []

    if expert_only:
        messages = [m for m in messages if m.is_expert]
        if not messages:
            return []

    # Build corpus matrix
    corpus_vecs = np.stack([m.embedding for m in messages])
    expert_mask = np.array([m.is_expert for m in messages])

    # Embed query
    query_vec = engine.embed(query)

    # Search
    results = EmbeddingEngine.search(
        query_vec, corpus_vecs, expert_mask, expert_boost, top_k
    )

    # Build results with email context
    search_results = []
    seen_emails = set()
    for idx, score in results:
        msg = messages[idx]
        # Deduplicate by email - show each issue thread once
        if msg.email_id in seen_emails:
            continue
        seen_emails.add(msg.email_id)

        email_record = store.get_email(msg.email_id)
        if email_record:
            search_results.append(SearchResult(
                message=msg, email=email_record, score=score
            ))

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
            # Show first 300 chars of the matching message
            preview = r.message.body_text[:300].replace("\n", "\n   ")
            lines.append(f"   Preview: {preview}")

        lines.append("")

    return "\n".join(lines)
