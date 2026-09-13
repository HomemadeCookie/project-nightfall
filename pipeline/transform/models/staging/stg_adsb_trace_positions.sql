{#
  globe_history traces exploded to one row per observed fix, clipped to the AOI.

  A segment in the bake stage still breaks wherever consecutive fixes of the same aircraft
  lapse past `MAX_TRACK_GAP_S`. This model does not join, interpolate, or invent a position.
  Altitude may be the string "ground", matching the live `/v2` quirk.
#}

with exploded as (

    select
        raw_object,
        collected_at,
        lower(trim(entity_id)) as entity_id,
        label,
        registration,
        entity_type,
        base_unix,
        unnest(cast(trace as json[])) as point
    from {{ ref('raw_adsb_traces') }}
    where entity_id is not null
        and entity_id <> ''

),

typed as (

    select
        raw_object,
        collected_at,
        entity_id,
        label,
        registration,
        entity_type,
        try_cast(point ->> 2 as double) as lon,
        try_cast(point ->> 1 as double) as lat,
        try_cast(point ->> 3 as double) as altitude_ft,
        (point ->> 3) = 'ground' as on_ground,
        try_cast(point ->> 4 as double) as speed_kt,
        try_cast(point ->> 5 as double) as track_deg,
        to_timestamp(
            base_unix + coalesce(try_cast(point ->> 0 as double), 0.0)
        ) as observed_at
    from exploded

)

select
    'adsb_lol' as source,
    'air' as mode,
    entity_id,
    label,
    registration,
    entity_type,
    lon,
    lat,
    altitude_ft,
    on_ground,
    speed_kt,
    track_deg,
    cast(null as smallint) as nav_status,
    observed_at,
    observed_at as observation_start,
    observed_at as observation_end,
    raw_object
from typed
where entity_id is not null
    and entity_id <> ''
    and lon is not null
    and lat is not null
    and {{ nightfall.in_aoi('lon', 'lat') }}
