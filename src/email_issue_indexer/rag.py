"""RAG layer: retrieve similar issues and synthesize expert analysis using Claude Code CLI."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile

from .embeddings import EmbeddingEngine
from .search import SearchResult, find_similar
from .store import Store


DEFAULT_SYSTEM_PROMPT = """\
You are an expert issue analyst. You help engineers learn from past issues \
by analyzing how experienced team members investigated and resolved similar problems.

You will be given:
1. A NEW ISSUE that needs analysis
2. SIMILAR PAST ISSUES with their full email threads, including how senior engineers investigated and resolved them

Your job is to:
- Identify the most likely root cause pattern based on how experts handled similar issues
- Explain the debugging approach the experts used and why
- Suggest concrete next steps for investigating the new issue
- Call out any patterns you see across multiple similar issues

Pay special attention to replies marked with [Expert] - these are from the team's most experienced engineers. \
Their reasoning, debugging methodology, and conclusions should carry the most weight.

Be specific and technical. Reference the similar issues by their subject lines when drawing parallels. \
If experts used specific tools, logs, or diagnostic commands, mention those."""


def _build_context(results: list[SearchResult], max_chars: int = 80000) -> str:
    """Build the context string from search results, respecting token limits."""
    sections = []
    total = 0
    for i, r in enumerate(results, 1):
        section = (
            f"## Similar Issue {i} (similarity: {r.score:.3f})\n\n"
            f"{r.email.markdown}"
        )
        if total + len(section) > max_chars:
            remaining = max_chars - total
            if remaining > 500:
                section = section[:remaining] + "\n\n[... truncated ...]"
                sections.append(section)
            break
        sections.append(section)
        total += len(section)
    return "\n\n---\n\n".join(sections)


def analyze(
    query: str,
    store: Store,
    engine: EmbeddingEngine,
    top_k: int = 5,
    expert_boost: float = 2.0,
    system_prompt: str | None = None,
) -> str | None:
    """Retrieve similar issues and ask Claude to analyze the new issue.

    Uses the `claude` CLI so it reuses the user's existing Claude Code auth.
    """
    # Step 1: Retrieve similar issues
    results = find_similar(
        query, store, engine, top_k=top_k, expert_boost=expert_boost
    )

    if not results:
        return "No similar issues found in the index. Try indexing more emails first."

    # Step 2: Build context
    context = _build_context(results)

    # Step 3: Build the prompt
    prompt = (
        f"# New Issue\n\n{query}\n\n"
        f"# Similar Past Issues\n\n{context}"
    )

    # Step 4: Call claude CLI with --print (non-interactive, streams to stdout)
    effective_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

    # Write prompt to a temp file to avoid shell escaping issues
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(prompt)
        prompt_file = f.name

    try:
        # Remove CLAUDECODE env var to allow nested invocation
        env = dict(__import__("os").environ)
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)

        # Read prompt from file and pass via stdin
        with open(prompt_file) as pf:
            prompt_text = pf.read()

        proc = subprocess.Popen(
            [
                "claude",
                "--print",
                "--append-system-prompt", effective_prompt,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

        # Send prompt via stdin and close it
        proc.stdin.write(prompt_text)
        proc.stdin.close()

        # Stream stdout line by line
        full_output = []
        for line in proc.stdout:
            print(line, end="", flush=True)
            full_output.append(line)

        proc.wait()

        if proc.returncode != 0:
            err = proc.stderr.read()
            print(f"\nError from claude CLI: {err}", file=sys.stderr)
            return None

        return "".join(full_output)

    finally:
        import os
        os.unlink(prompt_file)
