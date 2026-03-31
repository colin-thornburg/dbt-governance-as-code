with source_data as (
    select
        account_id,
        account_tier
    from {{ source('raw', 'accounts') }}
),
renamed as (
    select
        account_id,
        account_tier
    from source_data
)
select
    account_id,
    account_tier
from renamed
