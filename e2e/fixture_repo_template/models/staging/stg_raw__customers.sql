with source_data as (
    select
        customer_id,
        customer_name,
        account_id
    from {{ source('raw', 'customers') }}
),
renamed as (
    select
        customer_id,
        customer_name,
        account_id
    from source_data
)
select
    customer_id,
    customer_name,
    account_id
from renamed
