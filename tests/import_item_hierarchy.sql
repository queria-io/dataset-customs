-- import_item のコードの重複・親の欠落・コードの桁と階層の食い違いを検出する。0 行なら成功
select 'duplicate_code' as violation, code
from {{ ref('import_item') }}
group by code
having count(*) > 1

union all

select 'parent_not_found', c.code
from {{ ref('import_item') }} c
left join {{ ref('import_item') }} p on p.code = c.parent_code
where c.parent_code is not null and p.code is null

union all

select 'code_length_mismatch', code
from {{ ref('import_item') }}
where length(code) <> case level
    when 'chapter' then 2 when 'heading' then 4
    when 'subheading' then 6 when 'statistical' then 9 end
    or not starts_with(code, chapter_code)
