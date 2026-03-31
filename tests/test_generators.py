"""Tests for REVIEW.md and CLAUDE.md generators."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import dbt_governance.cli as cli_module
from dbt_governance.cli import app
from dbt_governance.config import GovernanceConfig
from dbt_governance.generators import generate_claude_md, generate_review_md, generate_reuse_md
from dbt_governance.scanner import ReuseRecommendation, ReuseReport, ScanResult, ScanSummary

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


def test_generate_reuse_md_includes_ranked_actions():
    result = ScanResult(
        project_name="Acme Analytics",
        timestamp="2026-03-25T10:00:00Z",
        summary=ScanSummary(),
        reuse_report=ReuseReport(
            total_recommendations=1,
            cluster_count=1,
            remaining_pair_count=0,
            prioritized_actions=[
                ReuseRecommendation(
                    recommendation_type="cluster",
                    priority="high",
                    confidence_band="high",
                    summary="Orders enrichment models form a reuse cluster.",
                    suggested_shared_model="int_orders_shared.sql",
                    model_names=["int_orders_enriched_a", "int_orders_enriched_b", "int_orders_enriched_c"],
                    cluster_average_score=0.88,
                    cluster_peak_score=0.93,
                    shared_inputs=["ref_stg_orders", "ref_stg_customers"],
                    shared_selected_columns=["order_id", "customer_id", "status"],
                    example_pairs=[
                        {
                            "left_model_name": "int_orders_enriched_a",
                            "right_model_name": "int_orders_enriched_b",
                            "similarity_score": 0.91,
                        }
                    ],
                )
            ],
            clusters=[],
            remaining_pairs=[],
        ),
    )

    content = generate_reuse_md(result)

    assert "# Reuse Remediation Report" in content
    assert "## Executive Summary" in content
    assert "Re-use remediation risk: Moderate" in content
    assert "Recommended leadership focus:" in content
    assert "Total recommendations: 1" in content
    assert "Orders enrichment models form a reuse cluster." in content
    assert "Suggested shared model: `int_orders_shared.sql`" in content
    assert "`int_orders_enriched_a` <-> `int_orders_enriched_b` (0.91)" in content


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


def test_generate_reuse_md_cli_writes_file(tmp_path: Path, monkeypatch):
    config_path = tmp_path / ".dbt-governance.yml"
    config_path.write_text(
        """\
version: 1
project:
  name: "Acme Analytics"
"""
    )
    output_path = tmp_path / "REUSE_REPORT.md"

    fake_result = ScanResult(
        project_name="Acme Analytics",
        timestamp="2026-03-25T10:00:00Z",
        summary=ScanSummary(),
        reuse_report=ReuseReport(
            total_recommendations=1,
            cluster_count=0,
            remaining_pair_count=1,
            prioritized_actions=[
                ReuseRecommendation(
                    recommendation_type="pair",
                    priority="medium",
                    confidence_band="medium",
                    summary="Two customer health models are highly similar.",
                    suggested_shared_model="int_customer_health_shared.sql",
                    model_names=["int_customer_health_a", "int_customer_health_b"],
                    similarity_score=0.79,
                    shared_inputs=["ref_stg_customers"],
                    shared_selected_columns=["customer_id", "health_score"],
                )
            ],
            clusters=[],
            remaining_pairs=[],
        ),
    )

    monkeypatch.setattr(cli_module, "run_scan", lambda **kwargs: fake_result)

    result = runner.invoke(
        app,
        ["generate", "reuse-md", "--config", str(config_path), "--output", str(output_path)],
    )

    assert result.exit_code == 0
    assert output_path.exists()
    assert "Reuse Remediation Report" in output_path.read_text()
    assert "int_customer_health_shared.sql" in output_path.read_text()
