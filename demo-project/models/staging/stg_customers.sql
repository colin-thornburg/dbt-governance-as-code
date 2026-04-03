WITH source AS (
    SELECT * FROM {{ source('ecommerce', 'raw_customers') }}
),

renamed AS (
    SELECT
        customer_id,
        name,
        email,
        plan,
        country,
        created_at
    FROM source
)

SELECT * FROM renamed
