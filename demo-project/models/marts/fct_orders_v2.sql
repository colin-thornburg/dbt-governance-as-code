-- GOVERNANCE ISSUE: identical_select_columns
-- Selects the exact same 6 columns from stg_orders as fct_orders.
-- Created as a quick "I need pending too" workaround — now there are
-- two maintained copies of effectively the same projection.
SELECT
    order_id,
    customer_id,
    status,
    amount,
    created_at,
    updated_at
FROM {{ ref('stg_orders') }}
WHERE status IN ('completed', 'pending')
