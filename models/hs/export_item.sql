{# pipelines/customs.py が最新の版から data/customs/export_item.csv に書き出す。 #}

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
from read_csv('data/customs/export_item.csv', header = true, all_varchar = true)
