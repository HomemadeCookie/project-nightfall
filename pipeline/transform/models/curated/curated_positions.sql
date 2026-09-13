{{
    config(
        materialized='external',
        location=var('curated_root') ~ '/v' ~ var('schema_version') ~ '/positions',
        format='parquet',
        options={
            'partition_by': 'dt, h3_partition',
            'overwrite_or_ignore': true,
            'compression': 'zstd',
        },
    )
}}

{#
  The curated mobility position store: GeoParquet, partitioned, schema-versioned.

  Partitioning is by date and by the *coarse* H3 parent, not by the coverage cell. Partitioning
  at the coverage resolution would scatter a single run across thousands of sub-megabyte files,
  which costs more in HTTP round trips and Pages file count than it saves in bytes scanned.
  The coverage cell travels as a sorted column instead, so Parquet row-group statistics give
  the pruning a deeper partition would have.

  Sorted by (h3_coverage, time_bucket, entity_id, observed_at) so those statistics are tight
  and so the file is byte-stable across reruns of the same inputs — which is the reproducibility
  half of the accuracy guarantee (README § Accuracy and Validation).
#}

select
    schema_version,
    source,
    mode,
    entity_id,
    label,
    registration,
    entity_type,
    lon,
    lat,
    geom,
    altitude_ft,
    on_ground,
    speed_kt,
    track_deg,
    nav_status,
    observed_at,
    time_bucket,
    h3_coverage,
    h3_coverage_resolution,
    raw_object,
    run_id,
    dt,
    h3_partition
from {{ ref('int_positions') }}
order by h3_coverage, time_bucket, entity_id, observed_at
