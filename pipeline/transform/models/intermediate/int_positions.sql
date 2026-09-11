{{ config(materialized='ephemeral') }}

{#
  The unified mobility position stream: aircraft and vessels in one shape.

  Ephemeral on purpose. Both curated models read it, and materialising it would mean the
  second one reads back a Parquet directory whose Hive partition columns it would have to
  reconstruct. Inlining keeps a single derivation of geometry, H3 cell, and time bucket.

  Deduplication is not optional. The adsb.lol coverage circles overlap, so one poll stores the
  same aircraft in several objects with an identical fix; counting those twice would inflate
  every observation count and, with it, every coverage figure derived from them. The key is
  (source, entity_id, observed_at) and the survivor is chosen by object name so the result is
  byte-stable across reruns.
#}

with unified as (

    select * from {{ ref('stg_adsb_positions') }}
    union all
    select * from {{ ref('stg_ais_positions') }}

),

deduplicated as (

    select *
    from unified
    qualify row_number() over (
        partition by source, entity_id, observed_at
        order by raw_object
    ) = 1

)

select
    {{ var('schema_version') }}::integer as schema_version,
    source,
    mode,
    entity_id,
    label,
    registration,
    entity_type,
    lon,
    lat,
    ST_Point(lon, lat) as geom,
    altitude_ft,
    on_ground,
    speed_kt,
    track_deg,
    nav_status,
    observed_at,
    {{ nightfall.time_bucket_of('observed_at') }} as time_bucket,
    -- Cells are named by role rather than by resolution, and the resolution travels as a
    -- column, so a file always states which grid it was built on (invariant 7) instead of
    -- relying on a column name that a changed var would quietly falsify.
    h3_h3_to_string(
        h3_latlng_to_cell(lat, lon, {{ var('coverage_h3_resolution') }})
    ) as h3_coverage,
    {{ var('coverage_h3_resolution') }}::smallint as h3_coverage_resolution,
    h3_h3_to_string(
        h3_latlng_to_cell(lat, lon, {{ var('partition_h3_resolution') }})
    ) as h3_partition,
    cast(observed_at as date) as dt,
    observation_start,
    observation_end,
    raw_object,
    '{{ var("run_id") }}' as run_id
from deduplicated
