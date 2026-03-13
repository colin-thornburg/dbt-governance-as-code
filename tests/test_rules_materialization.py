"""Tests for materialization rules."""

from __future__ import annotations

from dbt_governance.rules.materialization import (
    StagingMustBeViewRule,
)


class TestStagingMustBeView:
    def test_detects_non_view_staging(self, rule_context):
        rule = StagingMustBeViewRule()
        violations = rule.evaluate(rule_context)
        violation_names = {v.model_name for v in violations}
        assert "bad_model_no_prefix" in violation_names

    def test_passes_view_staging(self, rule_context):
        rule = StagingMustBeViewRule()
        violations = rule.evaluate(rule_context)
        violation_names = {v.model_name for v in violations}
        assert "stg_jaffle_shop__customers" not in violation_names
        assert "stg_jaffle_shop__orders" not in violation_names
