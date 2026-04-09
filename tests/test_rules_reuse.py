"""Tests for reuse and similarity detection rules."""

from __future__ import annotations

from dbt_governance.cloud.models import DAG, ManifestData, ModelNode
from dbt_governance.config import GovernanceConfig, Severity
from dbt_governance.rules.base import RuleContext, Violation
from dbt_governance.rules.reuse import DuplicateColumnDerivationsRule
from dbt_governance.rules.reuse import IdenticalSelectColumnsRule
from dbt_governance.scanner import _build_reuse_report
from dbt_governance.rules.reuse import ModelSimilarityCandidatesRule, ModelSimilarityClustersRule
from dbt_governance.rules.reuse import SharedCTECandidatesRule


def _model(
    unique_id: str,
    name: str,
    file_path: str,
    raw_code: str,
    depends_on_models: list[str],
    *,
    layer: str = "intermediate",
) -> ModelNode:
    return ModelNode(
        unique_id=unique_id,
        name=name,
        file_path=file_path,
        raw_code=raw_code,
        depends_on_models=depends_on_models,
        layer=layer,
    )


def test_model_similarity_candidates_flags_highly_similar_models():
    left = _model(
        "model.test.int_orders_enriched_a",
        "int_orders_enriched_a",
        "models/intermediate/int_orders_enriched_a.sql",
        """
with orders_base as (
    select
        order_id,
        customer_id,
        status,
        order_total
    from {{ ref('stg_orders') }}
),
customers_base as (
    select
        customer_id,
        segment
    from {{ ref('stg_customers') }}
),
joined_orders as (
    select
        orders_base.order_id,
        orders_base.customer_id,
        customers_base.segment,
        orders_base.status,
        orders_base.order_total
    from orders_base
    left join customers_base
        on orders_base.customer_id = customers_base.customer_id
    where orders_base.status = 'completed'
)
select
    order_id,
    customer_id,
    segment,
    status,
    order_total
from joined_orders
""",
        ["model.test.stg_orders", "model.test.stg_customers"],
    )
    right = _model(
        "model.test.int_orders_enriched_b",
        "int_orders_enriched_b",
        "models/intermediate/int_orders_enriched_b.sql",
        """
with order_rows as (
    select
        order_id,
        customer_id,
        status,
        order_total
    from {{ ref('stg_orders') }}
),
customer_rows as (
    select
        customer_id,
        segment
    from {{ ref('stg_customers') }}
),
enriched as (
    select
        order_rows.order_id,
        order_rows.customer_id,
        customer_rows.segment as segment,
        order_rows.status,
        order_rows.order_total
    from order_rows
    left join customer_rows
        on order_rows.customer_id = customer_rows.customer_id
    where order_rows.status = 'completed'
)
select
    order_id,
    customer_id,
    segment,
    status,
    order_total
from enriched
""",
        ["model.test.stg_orders", "model.test.stg_customers"],
    )
    unrelated = _model(
        "model.test.int_payments_daily",
        "int_payments_daily",
        "models/intermediate/int_payments_daily.sql",
        """
with payments as (
    select
        payment_id,
        payment_date,
        amount
    from {{ ref('stg_payments') }}
)
select
    payment_date,
    sum(amount) as total_amount
from payments
group by 1
""",
        ["model.test.stg_payments"],
    )

    manifest = ManifestData(
        models={
            left.unique_id: left,
            right.unique_id: right,
            unrelated.unique_id: unrelated,
        },
        dag=DAG(),
    )
    context = RuleContext(
        manifest_data=manifest,
        governance_config=GovernanceConfig(),
    )

    violations = ModelSimilarityCandidatesRule().evaluate(context)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.model_name in {"int_orders_enriched_a", "int_orders_enriched_b"}
    assert "highly similar" in violation.message
    assert "similarity score" in violation.message
    assert "int_orders_enriched_a" in violation.message
    assert "int_orders_enriched_b" in violation.message
    assert "shared logic" in violation.suggestion
    assert violation.details["confidence_band"] == "high"
    assert violation.details["paired_model_name"] in {"int_orders_enriched_a", "int_orders_enriched_b"}
    assert "ref_stg_customers" in violation.details["shared_inputs"]
    assert violation.details["suggested_shared_model"].endswith(".sql")


def test_model_similarity_candidates_respects_min_score_threshold():
    left = _model(
        "model.test.int_orders_summary",
        "int_orders_summary",
        "models/intermediate/int_orders_summary.sql",
        """
select
    order_id,
    customer_id,
    order_total
from {{ ref('stg_orders') }}
""",
        ["model.test.stg_orders"],
    )
    right = _model(
        "model.test.int_orders_status",
        "int_orders_status",
        "models/intermediate/int_orders_status.sql",
        """
select
    order_id,
    status,
    order_date
from {{ ref('stg_orders') }}
""",
        ["model.test.stg_orders"],
    )

    config = GovernanceConfig.model_validate(
        {
            "reuse": {
                "enabled": True,
                "rules": {
                    "model_similarity_candidates": {
                        "enabled": True,
                        "severity": "info",
                        "min_score": 0.95,
                    }
                },
            }
        }
    )
    manifest = ManifestData(models={left.unique_id: left, right.unique_id: right}, dag=DAG())
    context = RuleContext(manifest_data=manifest, governance_config=config)

    violations = ModelSimilarityCandidatesRule().evaluate(context)

    assert violations == []


def test_model_similarity_clusters_flags_reuse_group():
    model_a = _model(
        "model.test.int_orders_enriched_a",
        "int_orders_enriched_a",
        "models/intermediate/int_orders_enriched_a.sql",
        """
with orders_base as (
    select order_id, customer_id, status, order_total
    from {{ ref('stg_orders') }}
),
customers_base as (
    select customer_id, segment
    from {{ ref('stg_customers') }}
)
select
    orders_base.order_id,
    orders_base.customer_id,
    customers_base.segment,
    orders_base.status,
    orders_base.order_total
from orders_base
left join customers_base
    on orders_base.customer_id = customers_base.customer_id
where orders_base.status = 'completed'
""",
        ["model.test.stg_orders", "model.test.stg_customers"],
    )
    model_b = _model(
        "model.test.int_orders_enriched_b",
        "int_orders_enriched_b",
        "models/intermediate/int_orders_enriched_b.sql",
        """
with order_rows as (
    select order_id, customer_id, status, order_total
    from {{ ref('stg_orders') }}
),
customer_rows as (
    select customer_id, segment
    from {{ ref('stg_customers') }}
)
select
    order_rows.order_id,
    order_rows.customer_id,
    customer_rows.segment,
    order_rows.status,
    order_rows.order_total
from order_rows
left join customer_rows
    on order_rows.customer_id = customer_rows.customer_id
where order_rows.status = 'completed'
""",
        ["model.test.stg_orders", "model.test.stg_customers"],
    )
    model_c = _model(
        "model.test.int_orders_enriched_c",
        "int_orders_enriched_c",
        "models/intermediate/int_orders_enriched_c.sql",
        """
with source_orders as (
    select order_id, customer_id, status, order_total
    from {{ ref('stg_orders') }}
),
source_customers as (
    select customer_id, segment
    from {{ ref('stg_customers') }}
)
select
    source_orders.order_id,
    source_orders.customer_id,
    source_customers.segment,
    source_orders.status,
    source_orders.order_total
from source_orders
left join source_customers
    on source_orders.customer_id = source_customers.customer_id
where source_orders.status = 'completed'
""",
        ["model.test.stg_orders", "model.test.stg_customers"],
    )
    unrelated = _model(
        "model.test.int_payments_daily",
        "int_payments_daily",
        "models/intermediate/int_payments_daily.sql",
        """
select
    payment_date,
    sum(amount) as total_amount
from {{ ref('stg_payments') }}
group by 1
""",
        ["model.test.stg_payments"],
    )

    manifest = ManifestData(
        models={
            model_a.unique_id: model_a,
            model_b.unique_id: model_b,
            model_c.unique_id: model_c,
            unrelated.unique_id: unrelated,
        },
        dag=DAG(),
    )
    context = RuleContext(manifest_data=manifest, governance_config=GovernanceConfig())

    violations = ModelSimilarityClustersRule().evaluate(context)

    assert len(violations) == 1
    violation = violations[0]
    assert "reuse cluster" in violation.message
    assert violation.details["recommendation_type"] == "cluster"
    assert violation.details["cluster_size"] == 3
    assert set(violation.details["cluster_models"]) == {
        "int_orders_enriched_a",
        "int_orders_enriched_b",
        "int_orders_enriched_c",
    }
    assert violation.details["confidence_band"] in {"high", "medium"}
    assert violation.details["suggested_shared_model"].endswith(".sql")


def test_model_similarity_clusters_respects_min_cluster_size():
    left = _model(
        "model.test.int_orders_summary",
        "int_orders_summary",
        "models/intermediate/int_orders_summary.sql",
        """
select order_id, customer_id, order_total
from {{ ref('stg_orders') }}
""",
        ["model.test.stg_orders"],
    )
    right = _model(
        "model.test.int_orders_status",
        "int_orders_status",
        "models/intermediate/int_orders_status.sql",
        """
select order_id, customer_id, status
from {{ ref('stg_orders') }}
""",
        ["model.test.stg_orders"],
    )

    config = GovernanceConfig.model_validate(
        {
            "reuse": {
                "enabled": True,
                "rules": {
                    "model_similarity_candidates": {
                        "enabled": True,
                        "severity": "info",
                        "min_score": 0.50,
                    },
                    "model_similarity_clusters": {
                        "enabled": True,
                        "severity": "info",
                        "min_cluster_size": 3,
                    },
                },
            }
        }
    )
    manifest = ManifestData(models={left.unique_id: left, right.unique_id: right}, dag=DAG())
    context = RuleContext(manifest_data=manifest, governance_config=config)

    violations = ModelSimilarityClustersRule().evaluate(context)

    assert violations == []


def test_reuse_report_prioritizes_clusters_and_filters_covered_pairs():
    violations = [
        Violation(
            rule_id="reuse.model_similarity_clusters",
            severity=Severity.INFO,
            model_name="int_orders_enriched_a",
            file_path="models/intermediate/int_orders_enriched_a.sql",
            message="Cluster recommendation",
            details={
                "confidence_band": "high",
                "cluster_models": [
                    "int_orders_enriched_a",
                    "int_orders_enriched_b",
                    "int_orders_enriched_c",
                ],
                "cluster_size": 3,
                "cluster_average_score": 0.88,
                "cluster_peak_score": 0.93,
                "shared_inputs": ["ref_stg_orders", "ref_stg_customers"],
                "shared_selected_columns": ["order_id", "customer_id", "status"],
                "shared_aggregates": [],
                "shared_filters": ["status"],
                "suggested_shared_model": "int_ref_stg_customers_ref_stg_orders_shared.sql",
                "cluster_example_pairs": [
                    {
                        "left_model_name": "int_orders_enriched_a",
                        "right_model_name": "int_orders_enriched_b",
                        "similarity_score": 0.91,
                    }
                ],
            },
        ),
        Violation(
            rule_id="reuse.model_similarity_candidates",
            severity=Severity.INFO,
            model_name="int_orders_enriched_a",
            file_path="models/intermediate/int_orders_enriched_a.sql",
            message="Covered pair recommendation",
            details={
                "confidence_band": "high",
                "similarity_score": 0.91,
                "paired_model_name": "int_orders_enriched_b",
                "shared_inputs": ["ref_stg_orders"],
                "shared_selected_columns": ["order_id"],
                "shared_aggregates": [],
                "shared_filters": [],
                "suggested_shared_model": "int_orders_shared.sql",
            },
        ),
        Violation(
            rule_id="reuse.model_similarity_candidates",
            severity=Severity.INFO,
            model_name="int_customer_health_a",
            file_path="models/intermediate/int_customer_health_a.sql",
            message="Remaining pair recommendation",
            details={
                "confidence_band": "medium",
                "similarity_score": 0.79,
                "paired_model_name": "int_customer_health_b",
                "shared_inputs": ["ref_stg_customers"],
                "shared_selected_columns": ["customer_id", "health_score"],
                "shared_aggregates": ["avg"],
                "shared_filters": [],
                "suggested_shared_model": "int_customer_health_shared.sql",
            },
        ),
    ]

    report = _build_reuse_report(violations)

    assert report is not None
    assert report.cluster_count == 1
    assert report.remaining_pair_count == 1
    assert report.total_recommendations == 2
    assert report.prioritized_actions[0].recommendation_type == "cluster"
    assert report.remaining_pairs[0].primary_model_name == "int_customer_health_a"


def test_shared_cte_candidates_flags_equivalent_cte_logic_with_different_names():
    model_a = _model(
        "model.test.int_orders_enriched_a",
        "int_orders_enriched_a",
        "models/intermediate/int_orders_enriched_a.sql",
        """
with filtered_orders as (
    select
        order_id,
        customer_id,
        order_total
    from {{ ref('stg_orders') }}
    where order_total > 0
)
select
    order_id,
    customer_id,
    order_total
from filtered_orders
""",
        ["model.test.stg_orders"],
    )
    model_b = _model(
        "model.test.int_orders_enriched_b",
        "int_orders_enriched_b",
        "models/intermediate/int_orders_enriched_b.sql",
        """
with positive_orders as (
    select
        src.order_id,
        src.customer_id,
        src.order_total
    from {{ ref('stg_orders') }} as src
    where src.order_total > 0
)
select
    order_id,
    customer_id,
    order_total
from positive_orders
""",
        ["model.test.stg_orders"],
    )
    model_c = _model(
        "model.test.int_orders_enriched_c",
        "int_orders_enriched_c",
        "models/intermediate/int_orders_enriched_c.sql",
        """
with orders_ready as (
    select
        o.order_id,
        o.customer_id,
        o.order_total
    from {{ ref('stg_orders') }} as o
    where o.order_total > 0
)
select
    order_id,
    customer_id,
    order_total
from orders_ready
""",
        ["model.test.stg_orders"],
    )

    manifest = ManifestData(
        models={
            model_a.unique_id: model_a,
            model_b.unique_id: model_b,
            model_c.unique_id: model_c,
        },
        dag=DAG(),
    )
    context = RuleContext(manifest_data=manifest, governance_config=GovernanceConfig())

    violations = SharedCTECandidatesRule().evaluate(context)

    assert len(violations) == 3
    assert all("Equivalent CTE logic appears" in violation.message for violation in violations)
    assert all(
        set(violation.details["matching_cte_names"]) == {"filtered_orders", "orders_ready", "positive_orders"}
        for violation in violations
    )
    assert all(violation.details["suggested_shared_model"].endswith(".sql") for violation in violations)


def test_identical_select_columns_groups_same_inputs_and_columns():
    model_a = _model(
        "model.test.int_customer_projection_a",
        "int_customer_projection_a",
        "models/intermediate/int_customer_projection_a.sql",
        """
with customers as (
    select
        customer_id,
        first_name,
        last_name,
        email,
        country,
        created_at
    from {{ ref('stg_customers') }}
)
select
    customer_id,
    first_name,
    last_name,
    email,
    country,
    created_at
from customers
""",
        ["model.test.stg_customers"],
    )
    model_b = _model(
        "model.test.int_customer_projection_b",
        "int_customer_projection_b",
        "models/intermediate/int_customer_projection_b.sql",
        """
with base_rows as (
    select
        c.customer_id,
        c.first_name,
        c.last_name,
        c.email,
        c.country,
        c.created_at
    from {{ ref('stg_customers') }} as c
)
select
    customer_id,
    first_name,
    last_name,
    email,
    country,
    created_at
from base_rows
""",
        ["model.test.stg_customers"],
    )

    manifest = ManifestData(
        models={model_a.unique_id: model_a, model_b.unique_id: model_b},
        dag=DAG(),
    )
    context = RuleContext(manifest_data=manifest, governance_config=GovernanceConfig())

    violations = IdenticalSelectColumnsRule().evaluate(context)

    assert len(violations) == 2
    assert all("same 6 columns" in violation.message for violation in violations)
    assert all(violation.details["shared_inputs"] == ["ref_stg_customers"] for violation in violations)


def test_duplicate_column_derivations_flags_repeated_business_logic():
    model_a = _model(
        "model.test.fct_orders_a",
        "fct_orders_a",
        "models/marts/fct_orders_a.sql",
        """
select
    order_id,
    case
        when order_total >= 1000 then 'enterprise'
        when order_total >= 250 then 'growth'
        else 'self_serve'
    end as revenue_band
from {{ ref('stg_orders') }}
""",
        ["model.test.stg_orders"],
        layer="marts",
    )
    model_b = _model(
        "model.test.fct_orders_b",
        "fct_orders_b",
        "models/marts/fct_orders_b.sql",
        """
select
    o.order_id,
    case
        when o.order_total >= 1000 then 'enterprise'
        when o.order_total >= 250 then 'growth'
        else 'self_serve'
    end as revenue_band
from {{ ref('stg_orders') }} as o
""",
        ["model.test.stg_orders"],
        layer="marts",
    )
    model_c = _model(
        "model.test.fct_orders_c",
        "fct_orders_c",
        "models/marts/fct_orders_c.sql",
        """
select
    order_id,
    case
        when order_total >= 1000 then 'enterprise'
        when order_total >= 250 then 'growth'
        else 'self_serve'
    end as revenue_band
from {{ ref('stg_orders') }}
""",
        ["model.test.stg_orders"],
        layer="marts",
    )

    manifest = ManifestData(
        models={
            model_a.unique_id: model_a,
            model_b.unique_id: model_b,
            model_c.unique_id: model_c,
        },
        dag=DAG(),
    )
    context = RuleContext(manifest_data=manifest, governance_config=GovernanceConfig())

    violations = DuplicateColumnDerivationsRule().evaluate(context)

    assert len(violations) == 3
    assert all("Derived column 'revenue_band'" in violation.message for violation in violations)
    assert all(violation.details["derived_column_alias"] == "revenue_band" for violation in violations)
    assert all("case when order_total >= 1000" in violation.details["derived_expression"] for violation in violations)
