"""Tests for test coverage rules."""

from __future__ import annotations

from dbt_governance.rules.testing import (
    MartsHaveContractRule,
    MinimumTestCoverageRule,
    PrimaryKeyTestRequiredRule,
    StagingFreshnessRequiredRule,
)


class TestPrimaryKeyTestRequired:
    def test_passes_model_with_pk_tests(self, rule_context):
        rule = PrimaryKeyTestRequiredRule()
        violations = rule.evaluate(rule_context)
        violation_names = {v.model_name for v in violations}
        assert "stg_jaffle_shop__customers" not in violation_names
        assert "fct_orders" not in violation_names

    def test_detects_model_missing_pk_tests(self, rule_context):
        rule = PrimaryKeyTestRequiredRule()
        violations = rule.evaluate(rule_context)
        violation_names = {v.model_name for v in violations}
        assert "stg_stripe__payments" in violation_names
        assert "dim_customers" in violation_names


class TestMinimumTestCoverage:
    def test_detects_models_below_threshold(self, rule_context):
        rule = MinimumTestCoverageRule()
        violations = rule.evaluate(rule_context)
        low_test_names = {v.model_name for v in violations}
        assert "stg_stripe__payments" in low_test_names

    def test_passes_models_meeting_threshold(self, rule_context):
        rule = MinimumTestCoverageRule()
        violations = rule.evaluate(rule_context)
        violation_names = {v.model_name for v in violations}
        assert "stg_jaffle_shop__customers" not in violation_names
        assert "fct_orders" not in violation_names


class TestStagingFreshnessRequired:
    def test_detects_sources_without_freshness(self, rule_context):
        rule = StagingFreshnessRequiredRule()
        violations = rule.evaluate(rule_context)
        assert len(violations) >= 1
        violation_names = {v.model_name for v in violations}
        assert "stripe.payments" in violation_names or any("orders" in n for n in violation_names)


class TestMartsHaveContract:
    def test_detects_marts_without_contract(self, rule_context):
        rule = MartsHaveContractRule()
        violations = rule.evaluate(rule_context)
        violation_names = {v.model_name for v in violations}
        assert "fct_orders" in violation_names
        assert "dim_customers" in violation_names
