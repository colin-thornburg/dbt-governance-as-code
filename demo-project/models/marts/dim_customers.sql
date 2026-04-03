WITH customers AS (
    SELECT * FROM {{ ref('stg_customers') }}
),

order_summary AS (
    SELECT
        customer_id,
        COUNT(order_id)  AS total_orders,
        SUM(amount)      AS lifetime_value,
        MAX(created_at)  AS last_order_date
    FROM {{ ref('stg_orders') }}
    WHERE status = 'completed'
    GROUP BY 1
),

final AS (
    SELECT
        c.customer_id,
        c.name,
        c.email,
        c.plan,
        c.country,
        c.created_at          AS customer_since,
        COALESCE(o.total_orders, 0)    AS total_orders,
        COALESCE(o.lifetime_value, 0)  AS lifetime_value,
        o.last_order_date
    FROM customers c
    LEFT JOIN order_summary o ON c.customer_id = o.customer_id
)

SELECT * FROM final
