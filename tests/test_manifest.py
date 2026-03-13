"""Tests for manifest parsing."""

from __future__ import annotations

from pathlib import Path

from dbt_governance.manifest import load_manifest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestManifestParser:
    def test_loads_models(self, sample_manifest):
        assert len(sample_manifest.models) > 0
        assert "model.jaffle_shop.stg_jaffle_shop__customers" in sample_manifest.models

    def test_loads_sources(self, sample_manifest):
        assert len(sample_manifest.sources) == 3
        assert "source.jaffle_shop.jaffle_shop.customers" in sample_manifest.sources

    def test_loads_exposures(self, sample_manifest):
        assert len(sample_manifest.exposures) == 1

    def test_infers_layer_staging(self, sample_manifest):
        model = sample_manifest.models["model.jaffle_shop.stg_jaffle_shop__customers"]
        assert model.layer == "staging"

    def test_infers_layer_intermediate(self, sample_manifest):
        model = sample_manifest.models["model.jaffle_shop.int_payments_pivoted_to_orders"]
        assert model.layer == "intermediate"

    def test_infers_layer_marts(self, sample_manifest):
        model = sample_manifest.models["model.jaffle_shop.fct_orders"]
        assert model.layer == "marts"

    def test_builds_dag(self, sample_manifest):
        dag = sample_manifest.dag
        fct_orders_id = "model.jaffle_shop.fct_orders"
        parents = dag.nodes.get(fct_orders_id, [])
        assert len(parents) == 2

    def test_dag_depth(self, sample_manifest):
        dag = sample_manifest.dag
        depth = dag.depth("model.jaffle_shop.fct_orders")
        assert depth >= 2

    def test_dag_children(self, sample_manifest):
        dag = sample_manifest.dag
        stg_customers_id = "model.jaffle_shop.stg_jaffle_shop__customers"
        children = dag.children.get(stg_customers_id, [])
        assert len(children) >= 1

    def test_attaches_tests_to_models(self, sample_manifest):
        model = sample_manifest.models["model.jaffle_shop.stg_jaffle_shop__customers"]
        assert len(model.tests) == 2
        test_names = {t.name for t in model.tests}
        assert "unique_stg_jaffle_shop__customers_customer_id" in test_names

    def test_model_has_raw_code(self, sample_manifest):
        model = sample_manifest.models["model.jaffle_shop.stg_jaffle_shop__customers"]
        assert "source('jaffle_shop', 'customers')" in model.raw_code
