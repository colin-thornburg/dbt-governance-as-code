-- GOVERNANCE ISSUE: multiple_models_from_same_source
-- Reads raw_payments directly instead of through a staging model,
-- duplicating the source dependency already held by int_payment_analysis.
-- Fix: create stg_payments and have both models ref() it.
WITH payments AS (
    SELECT * FROM {{ source('ecommerce', 'raw_payments') }}
),

monthly_revenue AS (
    SELECT
        DATE_TRUNC('month', created_at) AS month,
        method,
        COUNT(payment_id)  AS transaction_count,
        SUM(amount)        AS gross_revenue,
        AVG(amount)        AS avg_transaction_value
    FROM payments
    WHERE status = 'succeeded'
    GROUP BY 1, 2
)

SELECT * FROM monthly_revenue
