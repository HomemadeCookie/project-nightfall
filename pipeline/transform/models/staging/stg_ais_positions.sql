{#
  AISStream vessel positions, typed and clipped to the AOI.

  Absolute time comes from the collector's receive stamp, not from the AIS payload:
  `PositionReport.Timestamp` is the UTC *second of the minute* of the fix (0-59, with 60-63
  reserved as status codes), so on its own it cannot place a position in time. It is left in
  the landing zone rather than carried here; a later schema version can pick it up to age a
  fix against its receive time, without reprocessing being any harder.

  Only `PositionReport` carries a position. `ShipStaticData` frames stay in the landing zone
  for later vessel-name enrichment and are filtered out here.

  These are sampled positions. NEVER join them into a continuous voyage (`.cursorrules` § 5).
#}

with reports as (

    select
        raw_object,
        collected_at,
        received_unix,
        frame -> 'Message' -> 'PositionReport' as report,
        frame -> 'MetaData' as metadata
    from {{ ref('raw_ais_frames') }}
    where frame ->> 'MessageType' = 'PositionReport'

),

typed as (

    select
        raw_object,
        collected_at,
        nullif(trim(coalesce(report ->> 'UserID', metadata ->> 'MMSI')), '') as entity_id,
        nullif(trim(metadata ->> 'ShipName'), '') as label,
        try_cast(coalesce(report ->> 'Longitude', metadata ->> 'Longitude') as double) as lon,
        try_cast(coalesce(report ->> 'Latitude', metadata ->> 'Latitude') as double) as lat,
        try_cast(report ->> 'Sog' as double) as speed_kt,
        try_cast(report ->> 'Cog' as double) as track_deg,
        try_cast(report ->> 'NavigationalStatus' as smallint) as nav_status,
        to_timestamp(received_unix) as observed_at
    from reports

)

select
    'aisstream' as source,
    'sea' as mode,
    entity_id,
    label,
    cast(null as varchar) as registration,
    cast(null as varchar) as entity_type,
    lon,
    lat,
    cast(null as double) as altitude_ft,
    -- AIS navigational status 5 is "moored" and 1 is "at anchor"; neither is "on the ground"
    -- in the aircraft sense, so this column stays null for vessels rather than being reused.
    cast(null as boolean) as on_ground,
    speed_kt,
    track_deg,
    nav_status,
    observed_at,
    -- The window closed at `collected_at` and ran for the declared sampling duration.
    collected_at - to_seconds({{ var('ais_window_s') }}) as observation_start,
    collected_at as observation_end,
    raw_object
from typed
where entity_id is not null
    and lon is not null
    and lat is not null
    and observed_at is not null
    and {{ nightfall.in_aoi('lon', 'lat') }}
