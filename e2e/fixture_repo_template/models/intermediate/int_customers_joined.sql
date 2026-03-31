with customers as (
    select
        customer_id,
        customer_name,
        account_id
    from {{ ref('stg_raw__customers') }}
),
accounts as (
    select
        account_id,
        account_tier
    from {{ ref('stg_raw__accounts') }}
),
joined as (
    select
        customers.customer_id,
        customers.customer_name,
        accounts.account_tier
    from customers
    left join accounts
        on customers.account_id = accounts.account_id
)
select
    customer_id,
    customer_name,
    account_tier
from joined
