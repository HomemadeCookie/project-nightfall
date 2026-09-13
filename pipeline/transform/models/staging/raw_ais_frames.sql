{#
  One row per stored AISStream frame.

  Stored lines are `{"received_unix": ..., "frame": <verbatim upstream frame>}`; the collector
  adds the receive time because no AIS position carries an absolute one (see
  `nightfall.sources.aisstream`). `collected_at` is when the sampling window closed, which is
  what bounds the window for coverage accounting.
#}

{% set globs = var('ais_globs') %}

{% if globs %}

select
    received_unix,
    frame,
    {{ nightfall.raw_object('filename') }} as raw_object,
    {{ nightfall.object_observed_at('filename') }} as collected_at
from read_json(
    {{ nightfall.sql_string_list(globs) }},
    columns = {'received_unix': 'DOUBLE', 'frame': 'JSON'},
    format = 'newline_delimited',
    filename = true
)

{% else %}

select
    cast(null as double) as received_unix,
    cast(null as json) as frame,
    cast(null as varchar) as raw_object,
    cast(null as timestamptz) as collected_at
where false

{% endif %}
