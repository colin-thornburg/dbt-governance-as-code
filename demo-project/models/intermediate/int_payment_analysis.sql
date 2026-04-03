-- GOVERNANCE ISSUE: multiple_models_from_same_source
-- Reads raw_payments directly instead of going through a staging model.
-- Both this model and fct_revenue reference the same raw source, meaning
-- any raw-layer changes must be fixed in two places.
WITH payments AS (
    SELECT * FROM {{ source('ecommerce', 'raw_payments') }}
),

summary AS (
    SELECT
        method,
        status,
        COUNT(payment_id)  AS payment_count,
        SUM(amount)        AS total_amount,
        AVG(amount)        AS avg_amount
    FROM payments
    GROUP BY 1, 2
)

SELECT * FROM summary
