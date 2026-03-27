"""Tests for Microsoft SafeLinks URL cleaning."""
from __future__ import annotations

from email_issue_indexer.safelinks import clean_safelink, clean_text


class TestCleanSafelink:
    def test_extracts_original_url(self):
        safelink = (
            "https://nam06.safelinks.protection.outlook.com/"
            "?url=https%3A%2F%2Fexample.com%2Fpage%3Fid%3D42"
            "&amp;data=05&amp;sdata=abc&amp;reserved=0"
        )
        assert clean_safelink(safelink) == "https://example.com/page?id=42"

    def test_returns_non_safelink_unchanged(self):
        url = "https://example.com/normal-page"
        assert clean_safelink(url) == url

    def test_returns_malformed_safelink_unchanged(self):
        url = "https://safelinks.protection.outlook.com/?nourl=1"
        assert clean_safelink(url) == url


class TestCleanText:
    def test_replaces_safelinks_in_text(self):
        text = (
            "Check this link: "
            "https://nam06.safelinks.protection.outlook.com/"
            "?url=https%3A%2F%2Fexample.com%2Fhelp"
            "&data=05 for details."
        )
        result = clean_text(text)
        assert "https://example.com/help" in result
        assert "safelinks" not in result

    def test_cleans_mailto_artifacts(self):
        text = "Contact <mailto:jane@example.com> for help."
        result = clean_text(text)
        assert result == "Contact (jane@example.com) for help."

    def test_handles_plain_text_unchanged(self):
        text = "No links here, just plain text."
        assert clean_text(text) == text
