"""Tests for DAG structure rules."""

from __future__ import annotations

from dbt_governance.rules.structure import (
    MartsNoSourceRefsRule,
    MaxDagDepthRule,
    ModelDirectoriesMatchLayersRule,
    NoOrphanModelsRule,
    StagingRefsSourceOnlyRule,
)


class TestStagingRefsSourceOnly:
    def test_detects_staging_model_reffing_another_model(self, rule_context):
        rule = StagingRefsSourceOnlyRule()
        violations = rule.evaluate(rule_context)
        bad_names = {v.model_name for v in violations}
        assert "bad_model_no_prefix" in bad_names

    def test_passes_staging_models_reffing_sources(self, rule_context):
        rule = StagingRefsSourceOnlyRule()
        violations = rule.evaluate(rule_context)
        violation_names = {v.model_name for v in violations}
        assert "stg_jaffle_shop__customers" not in violation_names
        assert "stg_jaffle_shop__orders" not in violation_names


class TestMartsNoSourceRefs:
    def test_passes_marts_not_reffing_sources(self, rule_context):
        rule = MartsNoSourceRefsRule()
        violations = rule.evaluate(rule_context)
        violation_names = {v.model_name for v in violations}
        assert "fct_orders" not in violation_names


class TestMaxDagDepth:
    def test_no_violations_with_default_threshold(self, rule_context):
        rule = MaxDagDepthRule()
        violations = rule.evaluate(rule_context)
        assert all(v.model_name != "stg_jaffle_shop__customers" for v in violations)


class TestNoOrphanModels:
    def test_detects_orphan_models(self, rule_context):
        rule = NoOrphanModelsRule()
        violations = rule.evaluate(rule_context)
        orphan_names = {v.model_name for v in violations}
        assert "bad_model_no_prefix" in orphan_names

    def test_exposure_endpoints_not_orphans(self, rule_context):
        rule = NoOrphanModelsRule()
        violations = rule.evaluate(rule_context)
        violation_names = {v.model_name for v in violations}
        assert "fct_orders" not in violation_names


class TestModelDirectoriesMatchLayers:
    def test_passes_correctly_placed_models(self, rule_context):
        rule = ModelDirectoriesMatchLayersRule()
        violations = rule.evaluate(rule_context)
        violation_names = {v.model_name for v in violations}
        assert "stg_jaffle_shop__customers" not in violation_names
        assert "int_payments_pivoted_to_orders" not in violation_names
        assert "fct_orders" not in violation_names
