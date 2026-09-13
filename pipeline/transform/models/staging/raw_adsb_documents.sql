{#
  One row per stored adsb.lol response.

  `adsb_globs` is computed by the CLI from the landing zone, so an empty list means a genuine
  cold start rather than a mistake. DuckDB raises on a glob that matches nothing, so the empty
  case is answered with a typed, empty relation instead. Every downstream model reads from
  here, which confines that branch to this file.
#}

{% set globs = var('adsb_globs') %}

{% if globs %}

select
    now as response_ms,
    ac as aircraft,
    {{ nightfall.raw_object('filename') }} as raw_object,
    {{ nightfall.object_observed_at('filename') }} as collected_at
from read_json(
    {{ nightfall.sql_string_list(globs) }},
    columns = {'now': 'DOUBLE', 'ac': 'JSON[]'},
    filename = true,
    ignore_errors = true
)
where now is not null
    and ac is not null

{% else %}

select
    cast(null as double) as response_ms,
    cast(null as json[]) as aircraft,
    cast(null as varchar) as raw_object,
    cast(null as timestamptz) as collected_at
where false

{% endif %}
