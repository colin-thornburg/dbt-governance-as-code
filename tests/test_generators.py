"""Tests for REVIEW.md and CLAUDE.md generators."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from dbt_governance.cli import app
from dbt_governance.config import GovernanceConfig
from dbt_governance.generators import generate_claude_md, generate_review_md

runner = CliRunner()


def test_generate_review_md_groups_rules_by_severity():
    config = GovernanceConfig()

    content = generate_review_md(config)

    assert "# dbt Governance Review Rules" in content
    assert "## Always Check (Error)" in content
    assert "Staging models must follow stg_<source>__<entity> naming" in content
    assert "## Scope" in content
    assert "Skip these paths: dbt_packages/, target/" in content


def test_generate_claude_md_includes_project_context():
    config = GovernanceConfig()

    content = generate_claude_md(config)

    assert "# dbt Project: dbt Project" in content
    assert "Preferred layer progression: staging -> intermediate -> marts." in content
    assert "- Staging: stg_{source}__{entity}" in content
    assert "CI fails on `error` severity or higher." in content


def test_generate_review_md_cli_writes_file(tmp_path: Path):
    config_path = tmp_path / ".dbt-governance.yml"
    config_path.write_text(
        """\
version: 1
project:
  name: "Acme Analytics"
naming:
  enabled: true
  rules:
    staging_prefix:
      enabled: true
      severity: error
      description: "Staging models must follow stg_<source>__<entity> naming"
"""
    )
    output_path = tmp_path / "REVIEW.md"

    result = runner.invoke(app, ["generate", "review-md", "--config", str(config_path), "--output", str(output_path)])

    assert result.exit_code == 0
    assert output_path.exists()
    assert "Acme Analytics" in output_path.read_text()


def test_generate_claude_md_cli_writes_file(tmp_path: Path):
    config_path = tmp_path / ".dbt-governance.yml"
    config_path.write_text(
        """\
version: 1
project:
  name: "Acme Analytics"
  description: "Warehouse governance rules"
dbt_cloud:
  enabled: true
  environment_id: 67890
  account_id: 12345
"""
    )
    output_path = tmp_path / "CLAUDE.md"

    result = runner.invoke(app, ["generate", "claude-md", "--config", str(config_path), "--output", str(output_path)])

    assert result.exit_code == 0
    assert output_path.exists()
    assert "dbt Cloud environment `67890`" in output_path.read_text()
