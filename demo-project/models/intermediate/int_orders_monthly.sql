-- GOVERNANCE ISSUE: model_similarity_candidates + model_similarity_clusters
-- Nearly identical to int_orders_daily and int_orders_weekly.
-- All three could be replaced by a single parameterised model or a
-- shared intermediate that downstream models aggregate at any granularity.
WITH active_orders AS (
    SELECT
        order_id,
        customer_id,
        status,
        amount,
        created_at
    FROM {{ ref('stg_orders') }}
    WHERE status != 'cancelled'
),

period_metrics AS (
    SELECT
        DATE_TRUNC('month', created_at) AS period,
        customer_id,
        COUNT(order_id)  AS order_count,
        SUM(amount)      AS total_revenue,
        AVG(amount)      AS avg_order_value
    FROM active_orders
    GROUP BY 1, 2
)

SELECT * FROM period_metrics
