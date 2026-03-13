"""Tests for documentation rules."""

from __future__ import annotations

from dbt_governance.rules.documentation import (
    ColumnDescriptionRequiredRule,
    ModelDescriptionRequiredRule,
    SourceDescriptionRequiredRule,
)


class TestModelDescriptionRequired:
    def test_detects_undocumented_marts(self, rule_context):
        rule = ModelDescriptionRequiredRule()
        violations = rule.evaluate(rule_context)
        violation_names = {v.model_name for v in violations}
        assert "dim_customers" in violation_names

    def test_passes_documented_models(self, rule_context):
        rule = ModelDescriptionRequiredRule()
        violations = rule.evaluate(rule_context)
        violation_names = {v.model_name for v in violations}
        assert "fct_orders" not in violation_names
        assert "int_payments_pivoted_to_orders" not in violation_names


class TestColumnDescriptionRequired:
    def test_detects_undocumented_columns(self, rule_context):
        rule = ColumnDescriptionRequiredRule()
        violations = rule.evaluate(rule_context)
        fct_violations = [v for v in violations if v.model_name == "fct_orders"]
        assert len(fct_violations) == 1
        assert "customer_id" in fct_violations[0].message or "total_amount" in fct_violations[0].message


class TestSourceDescriptionRequired:
    def test_detects_undocumented_sources(self, rule_context):
        rule = SourceDescriptionRequiredRule()
        violations = rule.evaluate(rule_context)
        violation_names = {v.model_name for v in violations}
        assert "stripe.payments" in violation_names

    def test_passes_documented_sources(self, rule_context):
        rule = SourceDescriptionRequiredRule()
        violations = rule.evaluate(rule_context)
        violation_names = {v.model_name for v in violations}
        assert "jaffle_shop.customers" not in violation_names
