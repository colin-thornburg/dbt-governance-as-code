"""Tests for the scanner orchestrator."""

from __future__ import annotations

from pathlib import Path

from dbt_governance.scanner import run_scan

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestRunScan:
    def test_scan_produces_results(self):
        result = run_scan(
            manifest_path=str(FIXTURES_DIR / "sample_manifest.json"),
            cloud_mode=False,
        )
        assert result.summary.models_scanned > 0
        assert result.summary.rules_evaluated > 0

    def test_scan_finds_violations(self):
        result = run_scan(
            manifest_path=str(FIXTURES_DIR / "sample_manifest.json"),
            cloud_mode=False,
        )
        assert len(result.violations) > 0

    def test_scan_computes_score(self):
        result = run_scan(
            manifest_path=str(FIXTURES_DIR / "sample_manifest.json"),
            cloud_mode=False,
        )
        assert 0 <= result.summary.score <= 100

    def test_scan_has_category_scores(self):
        result = run_scan(
            manifest_path=str(FIXTURES_DIR / "sample_manifest.json"),
            cloud_mode=False,
        )
        assert "naming" in result.summary.category_scores
        assert "structure" in result.summary.category_scores
        assert "testing" in result.summary.category_scores

    def test_scan_filters_by_category(self):
        result = run_scan(
            manifest_path=str(FIXTURES_DIR / "sample_manifest.json"),
            cloud_mode=False,
            rule_categories=["naming"],
        )
        for v in result.violations:
            assert v.rule_id.startswith("naming.")

    def test_scan_result_has_metadata(self):
        result = run_scan(
            manifest_path=str(FIXTURES_DIR / "sample_manifest.json"),
            cloud_mode=False,
        )
        assert result.scan_id
        assert result.timestamp
        assert result.is_cloud_mode is False
