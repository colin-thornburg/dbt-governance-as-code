with customer_dimension as (
    select
        customer_id,
        customer_name,
        account_tier
    from {{ ref('int_customers_joined') }}
),
final as (
    select
        customer_id,
        customer_name,
        account_tier
    from customer_dimension
)
select
    customer_id,
    customer_name,
    account_tier
from final
