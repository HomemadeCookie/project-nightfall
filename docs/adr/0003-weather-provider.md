# 0003. Open-Meteo for development, a commercial-safe provider before charging

**Status:** accepted, with a known blocker

## Context
Ferry-route risk needs forecast wind, gusts and waves at waypoints. Open-Meteo is keyless and fast, but its
free API is **non-commercial only**. ECMWF Open Data (CC BY 4.0) and NOAA GFS/WaveWatch III (public domain)
are commercial-safe but arrive as GRIB files that need `eccodes`/`cfgrib` and noticeably more code.

## Decision
Ship with the `open_meteo` adapter flagged `NON_COMMERCIAL`. The licence gate keeps every answer that
depends on it out of `--mode commercial`. The adapter emits a documented dataset (`route_forecast`), so a
`noaa_gfs` or `ecmwf_open` adapter can replace it without touching indicators or answers.

## Consequences
- `ferry.suspension` and `retail.stock_up` are research-only until the provider is swapped (or a paid
  Open-Meteo plan is bought and recorded in `reference/license_reviews.yaml`).
- Work to unblock: a GRIB adapter, sampling GFS 0.25 degree and WW3 at `ferry_waypoints()`. About a day of work.
