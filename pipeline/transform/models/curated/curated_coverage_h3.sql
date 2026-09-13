{{
    config(
        materialized='external',
        location=var('curated_root') ~ '/v' ~ var('schema_version') ~ '/coverage_h3',
        format='parquet',
        options={
            'overwrite_or_ignore': true,
            'compression': 'zstd',
        },
    )
}}

{#
  Coverage as a first-class dimension (README § Risks, coverage sparsity).

  Sampled mobility data looks identical to genuinely quiet water or sky, so no aggregate may
  travel without the evidence behind it. Every row carries how many observations it is built
  from, how many distinct entities they came from, how many stored samples contributed, and
  what fraction of the time bucket the source was actually observing.

  `sampled_duration_fraction` is computed from the declared observation interval of each stored
  object, overlapped with the bucket, not from the spread of the observations themselves —
  otherwise a fully monitored but quiet bucket would be indistinguishable from an unmonitored
  one, which is exactly the confusion the column exists to prevent.

  `receiver_coverage` is deliberately null in Phase 1. Neither adsb.lol nor AISStream publishes
  receiver locations, so there is nothing to compute it from; `coverage_model` says so in the
  data rather than leaving a plausible-looking number in its place. This is the temporal half
  of collection coverage only — the spatial half needs per-circle success accounting and a
  receiver model, both of which arrive with the insight stage that first depends on them.
#}

with positions as (

    select * from {{ ref('int_positions') }}

),

bucket_seconds as (

    select epoch(interval '{{ var("time_bucket") }}') as seconds

),

-- One row per stored object, carrying the interval it claims to have been observing.
samples as (

    select distinct
        source,
        raw_object,
        observation_start,
        observation_end
    from positions

),

buckets as (

    select distinct source, mode, time_bucket
    from positions

),

-- How much of each bucket the source was under observation, summed over the objects whose
-- intervals overlap it. Capped at the bucket length so overlapping samples cannot exceed 1.
sampled as (

    select
        b.source,
        b.mode,
        b.time_bucket,
        least(
            sum(
                epoch(
                    least(s.observation_end, b.time_bucket + interval '{{ var("time_bucket") }}')
                    - greatest(s.observation_start, b.time_bucket)
                )
            ),
            (select seconds from bucket_seconds)
        ) as sampled_seconds
    from buckets as b
    inner join samples as s
        on
            b.source = s.source
            and s.observation_end > b.time_bucket
            and s.observation_start < b.time_bucket + interval '{{ var("time_bucket") }}'
    group by b.source, b.mode, b.time_bucket

),

aggregated as (

    select
        schema_version,
        source,
        mode,
        h3_coverage,
        h3_coverage_resolution,
        time_bucket,
        count(*) as observation_count,
        count(distinct entity_id) as entity_count,
        count(distinct raw_object) as sample_count,
        avg(speed_kt) as mean_speed_kt,
        max(observed_at) as latest_observed_at,
        min(observed_at) as earliest_observed_at,
        any_value(run_id) as run_id
    from positions
    group by schema_version, source, mode, h3_coverage, h3_coverage_resolution, time_bucket

)

select
    a.schema_version,
    a.source,
    a.mode,
    a.h3_coverage,
    a.h3_coverage_resolution,
    a.time_bucket,
    a.observation_count,
    a.entity_count,
    a.sample_count,
    a.mean_speed_kt,
    a.earliest_observed_at,
    a.latest_observed_at,
    coalesce(s.sampled_seconds, 0.0) as sampled_seconds,
    coalesce(s.sampled_seconds, 0.0) / (select seconds from bucket_seconds)
        as sampled_duration_fraction,
    cast(null as double) as receiver_coverage,
    'unmodelled' as coverage_model,
    a.run_id
from aggregated as a
left join sampled as s
    on
        a.source = s.source
        and a.mode = s.mode
        and a.time_bucket = s.time_bucket
order by a.h3_coverage, a.time_bucket, a.source
