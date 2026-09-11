{#
  adsb.lol aircraft positions, typed and clipped to the AOI.

  Two wire quirks are handled here rather than downstream. `alt_baro` holds the string
  "ground" for an aircraft on the surface, so a plain cast would fail and `try_cast` yields
  null — which is the right altitude for a grounded aircraft anyway. `flight` is space-padded
  to eight characters, so an untrimmed callsign would not match the same aircraft between two
  polls.

  `seen_pos` is the age of the position fix in seconds. The fix was true then, not when the
  response was assembled, so it is subtracted from the response instant.

  How long one poll represents as observation time is *measured*, not assumed: adsb.lol
  documents no recency horizon, so the oldest fix a response still reported is the only
  evidence of how far back that response looked. In a quiet sky it reads short, which
  understates coverage rather than overstating it. `adsb_snapshot_horizon_max_s` caps it as a
  sanity ceiling, not as a claim about the provider.
#}

with exploded as (

    select
        response_ms,
        raw_object,
        collected_at,
        unnest(aircraft) as aircraft
    from {{ ref('raw_adsb_documents') }}

),

typed as (

    select
        raw_object,
        collected_at,
        lower(trim(aircraft ->> 'hex')) as entity_id,
        nullif(trim(aircraft ->> 'flight'), '') as label,
        nullif(trim(aircraft ->> 'r'), '') as registration,
        nullif(trim(aircraft ->> 't'), '') as entity_type,
        try_cast(aircraft ->> 'lon' as double) as lon,
        try_cast(aircraft ->> 'lat' as double) as lat,
        try_cast(aircraft ->> 'alt_baro' as double) as altitude_ft,
        (aircraft ->> 'alt_baro') = 'ground' as on_ground,
        try_cast(aircraft ->> 'gs' as double) as speed_kt,
        try_cast(aircraft ->> 'track' as double) as track_deg,
        to_timestamp(
            response_ms / {{ var('adsb_now_units_per_second') }}
            - coalesce(try_cast(aircraft ->> 'seen_pos' as double), 0.0)
        ) as observed_at,
        least(
            max(coalesce(try_cast(aircraft ->> 'seen_pos' as double), 0.0))
                over (partition by raw_object),
            {{ var('adsb_snapshot_horizon_max_s') }}
        ) as object_horizon_s
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
    collected_at - to_seconds(object_horizon_s) as observation_start,
    collected_at as observation_end,
    raw_object
from typed
where entity_id is not null
    and entity_id <> ''
    and lon is not null
    and lat is not null
    and {{ nightfall.in_aoi('lon', 'lat') }}
