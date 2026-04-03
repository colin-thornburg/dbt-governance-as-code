WITH source AS (
    SELECT * FROM {{ source('ecommerce', 'raw_orders') }}
),

renamed AS (
    SELECT
        order_id,
        customer_id,
        status,
        amount,
        created_at,
        updated_at
    FROM source
)

SELECT * FROM renamed
