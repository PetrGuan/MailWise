"""Tests for the mailwise init command."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from click.testing import CliRunner

from email_issue_indexer.cli import cli


class TestInit:
    def test_creates_config_with_defaults(self, tmp_path, monkeypatch):
        """Happy path: provide EML dir, skip experts."""
        monkeypatch.chdir(tmp_path)
        eml_dir = tmp_path / "emails"
        eml_dir.mkdir()

        runner = CliRunner()
        # Input: eml dir, yes use anyway (no .eml files), no experts
        result = runner.invoke(cli, ["--config", "config.yaml", "init"],
                               input=f"{eml_dir}\ny\nn\n")
        assert result.exit_code == 0
        assert "Config written" in result.output

        config = yaml.safe_load((tmp_path / "config.yaml").read_text())
        assert config["eml_directory"] == str(eml_dir)
        assert config["database"] == "data/index.db"
        assert config["embedding_model"] == "all-MiniLM-L6-v2"
        assert config["expert_boost"] == 1.5
        assert config["experts"] == []

        # Directories should be created
        assert (tmp_path / "data").is_dir()
        assert (tmp_path / "markdown").is_dir()

    def test_creates_config_with_experts(self, tmp_path, monkeypatch):
        """Provide EML dir and add one expert."""
        monkeypatch.chdir(tmp_path)
        eml_dir = tmp_path / "emails"
        eml_dir.mkdir()

        runner = CliRunner()
        # Input: eml dir, yes use anyway (no .eml files), yes add experts,
        # email, name, no more experts
        input_text = f"{eml_dir}\ny\ny\nalice@example.com\nAlice Smith\nn\n"
        result = runner.invoke(cli, ["--config", "config.yaml", "init"],
                               input=input_text)
        assert result.exit_code == 0

        config = yaml.safe_load((tmp_path / "config.yaml").read_text())
        assert len(config["experts"]) == 1
        assert config["experts"][0]["email"] == "alice@example.com"
        assert config["experts"][0]["name"] == "Alice Smith"

    def test_aborts_if_config_exists_and_no_overwrite(self, tmp_path, monkeypatch):
        """Existing config + decline overwrite = abort."""
        monkeypatch.chdir(tmp_path)
        config_path = tmp_path / "config.yaml"
        config_path.write_text("existing: true")

        runner = CliRunner()
        result = runner.invoke(cli, ["--config", "config.yaml", "init"],
                               input="n\n")
        assert result.exit_code == 0
        assert "Aborted" in result.output
        # Original config unchanged
        assert "existing: true" in config_path.read_text()

    def test_overwrites_existing_config(self, tmp_path, monkeypatch):
        """Existing config + confirm overwrite = new config."""
        monkeypatch.chdir(tmp_path)
        config_path = tmp_path / "config.yaml"
        config_path.write_text("old: true")
        eml_dir = tmp_path / "emails"
        eml_dir.mkdir()

        runner = CliRunner()
        # Input: yes overwrite, eml dir, yes use anyway (no .eml files), no experts
        result = runner.invoke(cli, ["--config", "config.yaml", "init"],
                               input=f"y\n{eml_dir}\ny\nn\n")
        assert result.exit_code == 0
        assert "Config written" in result.output
        config = yaml.safe_load(config_path.read_text())
        assert "old" not in config

    def test_creates_missing_eml_directory(self, tmp_path, monkeypatch):
        """Offer to create EML directory if it doesn't exist."""
        monkeypatch.chdir(tmp_path)
        eml_dir = tmp_path / "my_emails"

        runner = CliRunner()
        # Input: nonexistent dir, yes create it, no experts
        result = runner.invoke(cli, ["--config", "config.yaml", "init"],
                               input=f"{eml_dir}\ny\nn\n")
        assert result.exit_code == 0
        assert eml_dir.is_dir()
        assert "Created" in result.output

    def test_shows_eml_count(self, tmp_path, monkeypatch):
        """Shows count of .eml files found in directory."""
        monkeypatch.chdir(tmp_path)
        eml_dir = tmp_path / "emails"
        eml_dir.mkdir()
        (eml_dir / "test1.eml").write_text("From: a@example.com\n\nBody")
        (eml_dir / "test2.eml").write_text("From: b@example.com\n\nBody")

        runner = CliRunner()
        result = runner.invoke(cli, ["--config", "config.yaml", "init"],
                               input=f"{eml_dir}\nn\nn\n")
        assert result.exit_code == 0
        assert "Found 2 .eml files" in result.output
