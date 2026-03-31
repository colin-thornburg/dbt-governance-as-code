"""Tests for the scanner orchestrator."""

from __future__ import annotations

from pathlib import Path

import pytest

from dbt_governance.ai.engine import AIReviewEngine, TokenUsage
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
        assert "migration" in result.summary.category_scores
        assert "reuse" in result.summary.category_scores

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

    def test_with_ai_auto_selects_openai_when_key_present(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        captured: dict[str, str | bool] = {}

        async def fake_review_all(self: AIReviewEngine, manifest_data, changed_files=None):  # noqa: ANN001
            captured["enabled"] = self.config.ai_review.enabled
            captured["provider"] = self.config.ai_review.provider.value
            captured["model"] = self.config.ai_review.model
            return [], TokenUsage(provider=self.config.ai_review.provider.value, model=self.config.ai_review.model)

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
        monkeypatch.setattr(AIReviewEngine, "review_all", fake_review_all)

        result = run_scan(
            manifest_path=str(FIXTURES_DIR / "sample_manifest.json"),
            cloud_mode=False,
            with_ai=True,
        )

        assert captured["enabled"] is True
        assert captured["provider"] == "openai"
        assert captured["model"] == "gpt-5.4"
        assert result.token_usage is not None

    def test_changed_only_filters_reported_violations(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            "dbt_governance.scanner.get_changed_files",
            lambda project_dir: ["models/marts/finance/fct_orders.sql"],
        )

        result = run_scan(
            manifest_path=str(FIXTURES_DIR / "sample_manifest.json"),
            cloud_mode=False,
            changed_only=True,
        )

        assert result.violations
        assert any(violation.file_path == "models/marts/finance" for violation in result.violations)
        assert all(
            violation.file_path == "models/marts/finance/fct_orders.sql"
            or violation.file_path == "models/marts/finance"
            for violation in result.violations
        )
