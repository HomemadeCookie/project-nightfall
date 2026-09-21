{#
  One row per stored adsb.lol globe_history trace.

  The same landing-zone globs as `raw_adsb_documents`: live `/v2/point` snapshots have no
  `trace` field and are dropped here, while history traces have no `ac` field and are dropped
  there. `ignore_errors` is required so a mixed partition does not fail the read.
#}

{% set globs = var('adsb_globs') %}

{% if globs %}

select
    timestamp as base_unix,
    coalesce(nullif(trim(hex), ''), nullif(trim(icao), '')) as entity_id,
    nullif(trim(flight), '') as label,
    nullif(trim(r), '') as registration,
    nullif(trim(t), '') as entity_type,
    trace,
    {{ nightfall.raw_object('filename') }} as raw_object,
    {{ nightfall.object_observed_at('filename') }} as collected_at
from read_json(
    {{ nightfall.sql_string_list(globs) }},
    columns = {
        'timestamp': 'DOUBLE',
        'icao': 'VARCHAR',
        'hex': 'VARCHAR',
        'r': 'VARCHAR',
        't': 'VARCHAR',
        'flight': 'VARCHAR',
        'trace': 'JSON'
    },
    filename = true,
    ignore_errors = true
)
where timestamp is not null
    and trace is not null

{% else %}

select
    cast(null as double) as base_unix,
    cast(null as varchar) as entity_id,
    cast(null as varchar) as label,
    cast(null as varchar) as registration,
    cast(null as varchar) as entity_type,
    cast(null as json) as trace,
    cast(null as varchar) as raw_object,
    cast(null as timestamptz) as collected_at
where false

{% endif %}
