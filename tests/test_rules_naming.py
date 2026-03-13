"""Tests for naming convention rules."""

from __future__ import annotations

from dbt_governance.rules.naming import (
    IntermediatePrefixRule,
    MartsPrefixRule,
    ModelFileMatchesNameRule,
    StagingPrefixRule,
)


class TestStagingPrefix:
    def test_detects_bad_staging_name(self, rule_context):
        rule = StagingPrefixRule()
        violations = rule.evaluate(rule_context)
        bad_names = {v.model_name for v in violations}
        assert "bad_model_no_prefix" in bad_names

    def test_passes_correct_staging_name(self, rule_context):
        rule = StagingPrefixRule()
        violations = rule.evaluate(rule_context)
        passing_names = {v.model_name for v in violations}
        assert "stg_jaffle_shop__customers" not in passing_names
        assert "stg_jaffle_shop__orders" not in passing_names


class TestIntermediatePrefix:
    def test_passes_correct_intermediate_name(self, rule_context):
        rule = IntermediatePrefixRule()
        violations = rule.evaluate(rule_context)
        violation_names = {v.model_name for v in violations}
        assert "int_payments_pivoted_to_orders" not in violation_names


class TestMartsPrefix:
    def test_passes_fct_prefix(self, rule_context):
        rule = MartsPrefixRule()
        violations = rule.evaluate(rule_context)
        violation_names = {v.model_name for v in violations}
        assert "fct_orders" not in violation_names

    def test_passes_dim_prefix(self, rule_context):
        rule = MartsPrefixRule()
        violations = rule.evaluate(rule_context)
        violation_names = {v.model_name for v in violations}
        assert "dim_customers" not in violation_names


class TestModelFileMatchesName:
    def test_passes_matching_files(self, rule_context):
        rule = ModelFileMatchesNameRule()
        violations = rule.evaluate(rule_context)
        violation_names = {v.model_name for v in violations}
        assert "stg_jaffle_shop__customers" not in violation_names
