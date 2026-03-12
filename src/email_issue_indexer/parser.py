"""Parse EML files and split email threads into individual messages."""
from __future__ import annotations

import email
import hashlib
import re
from dataclasses import dataclass, field
from email import policy
from pathlib import Path

from .safelinks import clean_text


@dataclass
class ThreadMessage:
    from_name: str
    from_addr: str
    sent_date: str | None
    to_addrs: str | None
    subject: str | None
    body: str
    position: int  # 0 = most recent reply


@dataclass
class ParsedEmail:
    file_path: str
    file_hash: str
    subject: str
    date: str
    from_name: str
    from_addr: str
    to_addrs: list[str]
    message_id: str
    in_reply_to: str | None
    messages: list[ThreadMessage] = field(default_factory=list)


def hash_file(path: Path) -> str:
    """SHA256 hash of file contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_addr(addr_str: str | None) -> tuple[str, str]:
    """Extract (name, email) from 'Name <email>' format."""
    if not addr_str:
        return ("", "")
    # Clean mailto artifacts like "addr@x.com(addr@x.com)" anywhere
    addr_str = re.sub(r'\([^)]*@[^)]*\)', '', addr_str).strip()
    match = re.search(r'(.+?)\s*<([^>]+)>', addr_str)
    if match:
        return (match.group(1).strip().strip('"'), match.group(2).strip())
    # Bare email
    return ("", addr_str.strip())


def _extract_addr_list(addr_str: str | None) -> list[str]:
    """Extract list of email addresses from To/Cc header."""
    if not addr_str:
        return []
    return [a.strip() for a in re.findall(r'[\w.+-]+@[\w.-]+', addr_str)]


# Pattern to split Outlook-style inline thread replies.
# Matches a separator line of underscores followed by From:/Sent: block,
# or just From: followed by Sent: (some clients omit the underscores).
THREAD_HEADER = re.compile(
    r'(?:^[_\-]{5,}\s*$\n)?'       # Optional separator line
    r'^From:\s+(.+?)$\n'            # From line
    r'^Sent:\s+(.+?)$\n'            # Sent line
    r'(?:^To:\s+(.+?)$\n)?'         # Optional To line
    r'(?:^Cc:\s+(.+?)$\n)?'         # Optional Cc line
    r'(?:^Subject:\s+(.+?)$\n)?',   # Optional Subject line
    re.MULTILINE
)


def _split_thread(text: str) -> list[ThreadMessage]:
    """Split an email body into individual thread messages."""
    messages = []

    # Find all thread headers
    splits = list(THREAD_HEADER.finditer(text))

    if not splits:
        # Single message, no thread
        body = text.strip()
        if body:
            messages.append(ThreadMessage(
                from_name="", from_addr="", sent_date=None,
                to_addrs=None, subject=None, body=body, position=0
            ))
        return messages

    # Text before first split is the top-level reply
    top_body = text[:splits[0].start()].strip()
    if top_body:
        messages.append(ThreadMessage(
            from_name="", from_addr="", sent_date=None,
            to_addrs=None, subject=None, body=top_body, position=0
        ))

    for i, match in enumerate(splits):
        from_raw = match.group(1) or ""
        sent_date = match.group(2)
        to_addrs = match.group(3)
        subject = match.group(5)

        from_name, from_addr = _extract_addr(from_raw)
        if not from_addr and from_raw:
            from_name = from_raw.strip()

        # Body is from end of this header to start of next header (or end of text)
        body_start = match.end()
        body_end = splits[i + 1].start() if i + 1 < len(splits) else len(text)

        # Remove leading separator lines from body
        body = text[body_start:body_end].strip()
        # Remove trailing separator lines
        body = re.sub(r'\n[_\-]{5,}\s*$', '', body).strip()

        messages.append(ThreadMessage(
            from_name=from_name,
            from_addr=from_addr,
            sent_date=sent_date.strip() if sent_date else None,
            to_addrs=to_addrs.strip() if to_addrs else None,
            subject=subject.strip() if subject else None,
            body=body,
            position=len(messages)
        ))

    return messages


def parse_eml(path: Path) -> ParsedEmail:
    """Parse an EML file into structured data with thread messages."""
    file_hash = hash_file(path)

    with open(path, "rb") as f:
        msg = email.message_from_binary_file(f, policy=policy.default)

    subject = msg["Subject"] or ""
    date = msg["Date"] or ""
    from_name, from_addr = _extract_addr(msg["From"])
    to_addrs = _extract_addr_list(msg["To"])
    message_id = msg["Message-ID"] or ""
    in_reply_to = msg["In-Reply-To"]

    # Extract plain text body
    body_text = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    body_text = part.get_content()
                except Exception:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body_text = payload.decode("utf-8", errors="replace")
                break
    else:
        try:
            body_text = msg.get_content()
        except Exception:
            payload = msg.get_payload(decode=True)
            if payload:
                body_text = payload.decode("utf-8", errors="replace")

    # Clean safelinks and mailto artifacts
    body_text = clean_text(body_text)

    # Split into thread messages
    thread_messages = _split_thread(body_text)

    # Fill in top-level message metadata from email headers
    if thread_messages and not thread_messages[0].from_addr:
        thread_messages[0].from_name = from_name
        thread_messages[0].from_addr = from_addr
        thread_messages[0].sent_date = str(date)

    parsed = ParsedEmail(
        file_path=str(path),
        file_hash=file_hash,
        subject=subject,
        date=str(date),
        from_name=from_name,
        from_addr=from_addr,
        to_addrs=to_addrs,
        message_id=message_id,
        in_reply_to=in_reply_to,
        messages=thread_messages,
    )

    return parsed
