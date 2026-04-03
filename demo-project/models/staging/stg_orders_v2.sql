-- GOVERNANCE ISSUE: duplicate_source_staging
-- This model stages the same raw_orders source as stg_orders.
-- These two should be merged into one canonical staging model.
WITH source AS (
    SELECT * FROM {{ source('ecommerce', 'raw_orders') }}
),

enriched AS (
    SELECT
        order_id,
        customer_id,
        UPPER(status) AS status,
        amount,
        amount * 0.1 AS tax_amount,
        created_at,
        updated_at
    FROM source
    WHERE amount > 0
)

SELECT * FROM enriched
