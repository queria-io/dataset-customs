select
    cast(edition as date) as edition,
    level,
    code,
    hs_code,
    nullif(parent_code, '') as parent_code,
    chapter_code,
    name,
    full_name,
    nullif(unit_1, '') as unit_1,
    nullif(unit_2, '') as unit_2,
    source_url
from {{ ref('raw_export_item') }}
