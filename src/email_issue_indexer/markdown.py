"""Convert parsed email threads to AI-friendly markdown."""
from __future__ import annotations

from .parser import ParsedEmail


def to_markdown(parsed: ParsedEmail, expert_emails: set[str] | None = None) -> str:
    """Convert a ParsedEmail to structured markdown."""
    experts = expert_emails or set()
    lines = []

    # Title
    subject = parsed.subject.strip()
    lines.append(f"# {subject}")
    lines.append("")

    # Metadata
    lines.append(f"**Date:** {parsed.date}")
    # Collect unique participants
    participants = set()
    for msg in parsed.messages:
        if msg.from_name:
            participants.add(msg.from_name)
        elif msg.from_addr:
            participants.add(msg.from_addr)
    if parsed.from_name:
        participants.add(parsed.from_name)
    if participants:
        lines.append(f"**Participants:** {', '.join(sorted(participants))}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Thread messages
    for i, msg in enumerate(parsed.messages):
        name = msg.from_name or msg.from_addr or "Unknown"
        addr = f" ({msg.from_addr})" if msg.from_addr else ""
        is_expert = msg.from_addr and msg.from_addr.lower() in experts
        expert_tag = " **[Expert]**" if is_expert else ""

        lines.append(f"## Reply {i + 1} -- {name}{addr}{expert_tag}")

        if msg.sent_date:
            lines.append(f"**Date:** {msg.sent_date}")
        lines.append("")
        lines.append(msg.body)
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)
