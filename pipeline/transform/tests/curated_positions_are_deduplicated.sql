-- The adsb.lol coverage circles overlap, so one poll stores the same aircraft in several
-- objects with an identical fix. If deduplication regresses, nothing breaks loudly: every
-- observation count simply inflates, and with it every coverage figure derived from one.

select
    source,
    entity_id,
    observed_at,
    count(*) as occurrences
from {{ ref('curated_positions') }}
where entity_id is not null
group by source, entity_id, observed_at
having count(*) > 1
