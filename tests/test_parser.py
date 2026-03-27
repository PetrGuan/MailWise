"""Tests for EML parsing and thread splitting."""
from __future__ import annotations

from pathlib import Path

from email_issue_indexer.parser import (
    _extract_addr,
    _extract_addr_list,
    _split_thread,
    file_stat,
    hash_file,
    parse_eml,
)


class TestExtractAddr:
    def test_name_and_email(self):
        name, addr = _extract_addr("Jane Doe <jane@example.com>")
        assert name == "Jane Doe"
        assert addr == "jane@example.com"

    def test_quoted_name(self):
        name, addr = _extract_addr('"Jane Doe" <jane@example.com>')
        assert name == "Jane Doe"
        assert addr == "jane@example.com"

    def test_bare_email(self):
        name, addr = _extract_addr("jane@example.com")
        assert name == ""
        assert addr == "jane@example.com"

    def test_none_input(self):
        name, addr = _extract_addr(None)
        assert name == ""
        assert addr == ""

    def test_mailto_artifact_cleaned(self):
        name, addr = _extract_addr("jane@example.com(jane@example.com)")
        assert addr == "jane@example.com"


class TestExtractAddrList:
    def test_multiple_addresses(self):
        addrs = _extract_addr_list("alice@example.com, bob@example.com")
        assert addrs == ["alice@example.com", "bob@example.com"]

    def test_empty_input(self):
        assert _extract_addr_list(None) == []
        assert _extract_addr_list("") == []


class TestSplitThread:
    def test_single_message(self):
        messages = _split_thread("Just a simple body with no thread headers.")
        assert len(messages) == 1
        assert messages[0].position == 0
        assert "simple body" in messages[0].body

    def test_outlook_thread(self):
        text = (
            "Top reply content here.\n\n"
            "________________________________\n"
            "From: Bob Chen <bob@example.com>\n"
            "Sent: Tuesday, March 11, 2025 8:30 AM\n"
            "To: support@example.com\n"
            "Subject: RE: Some issue\n"
            "\n"
            "Bob's earlier message.\n"
        )
        messages = _split_thread(text)
        assert len(messages) == 2
        assert "Top reply" in messages[0].body
        assert messages[1].from_addr == "bob@example.com"
        assert "Bob's earlier" in messages[1].body

    def test_empty_text(self):
        messages = _split_thread("")
        assert messages == []


class TestFileStat:
    def test_returns_mtime_and_size(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        mtime, size = file_stat(f)
        assert isinstance(mtime, float)
        assert size == 5


class TestHashFile:
    def test_consistent_hash(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        h1 = hash_file(f)
        h2 = hash_file(f)
        assert h1 == h2
        assert len(h1) == 64  # SHA256 hex digest


class TestParseEml:
    def test_simple_eml(self, sample_eml_path):
        result = parse_eml(sample_eml_path)
        assert result.subject == "Sync failure after migration"
        assert result.from_addr == "jane.doe@example.com"
        assert result.from_name == "Jane Doe"
        assert "support@example.com" in result.to_addrs
        assert result.message_id == "<msg001@example.com>"
        assert len(result.messages) >= 1
        assert "0x800CCC0E" in result.messages[0].body

    def test_threaded_eml(self, threaded_eml_path):
        result = parse_eml(threaded_eml_path)
        assert result.subject == "RE: Database timeout on reporting queries"
        assert result.in_reply_to == "<msg001@example.com>"
        # Should have 3 messages: top reply + 2 thread splits
        assert len(result.messages) == 3
        # First message (top reply) should be from the EML header sender
        assert result.messages[0].from_addr == "alice@example.com"
