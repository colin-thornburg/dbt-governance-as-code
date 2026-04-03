-- GOVERNANCE ISSUE: identical_select_columns
-- Selects the exact same 6 columns from stg_orders as fct_orders_v2.
-- The only difference is the WHERE clause. These should be one model
-- with consumers filtering on status themselves, or a single wide
-- fact table that serves both use-cases.
SELECT
    order_id,
    customer_id,
    status,
    amount,
    created_at,
    updated_at
FROM {{ ref('stg_orders') }}
WHERE status = 'completed'
