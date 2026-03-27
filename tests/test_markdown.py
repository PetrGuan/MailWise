"""Tests for markdown conversion and expert tagging."""
from __future__ import annotations

from email_issue_indexer.markdown import to_markdown
from email_issue_indexer.parser import parse_eml


class TestToMarkdown:
    def test_contains_subject_as_heading(self, sample_eml_path):
        parsed = parse_eml(sample_eml_path)
        md = to_markdown(parsed)
        assert "# Sync failure after migration" in md

    def test_contains_participants(self, sample_eml_path):
        parsed = parse_eml(sample_eml_path)
        md = to_markdown(parsed)
        assert "**Participants:**" in md
        assert "Jane Doe" in md

    def test_contains_reply_sections(self, threaded_eml_path):
        parsed = parse_eml(threaded_eml_path)
        md = to_markdown(parsed)
        assert "## Reply 1" in md
        assert "## Reply 2" in md
        assert "## Reply 3" in md

    def test_expert_tagging(self, threaded_eml_path):
        parsed = parse_eml(threaded_eml_path)
        expert_emails = {"bob@example.com"}
        md = to_markdown(parsed, expert_emails)
        assert "**[Expert]**" in md
        # Only Bob should be tagged, not others
        assert md.count("**[Expert]**") == 1

    def test_no_experts_no_tags(self, threaded_eml_path):
        parsed = parse_eml(threaded_eml_path)
        md = to_markdown(parsed, expert_emails=set())
        assert "[Expert]" not in md
