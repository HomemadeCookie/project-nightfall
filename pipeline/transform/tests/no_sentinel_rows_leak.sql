-- dbt-duckdb writes one all-null row when an external model is empty, so the Parquet file
-- still carries a schema. That is acceptable as the entire contents of a cold-start file and
-- unacceptable alongside real data, where it would be counted as an observation with no
-- position, no time, and no provenance.

select count(*) as sentinel_rows
from {{ ref('curated_positions') }}
where entity_id is null
having count(*) > 0 and (select count(*) from {{ ref('curated_positions') }}) > 1
