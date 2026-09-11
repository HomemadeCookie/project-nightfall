# project-nightfall

### Summary
A data-driven supply chain insights generator for the Philippines, designed to navigate its unique geographic and climate challenges. It produces actionable insights on the best course of action over a period of months and years, based on satellite and mobility data.

### Problem Statement
Businesses in the Philippines often take losses as a given during every typhoon season, absorbing the financial hit. Without a reliable way to understand the intersection of weather patterns and the entire supply chain, businesses are essentially flying blind.

### Success Metrics
* **Improved Decision-Making:** Businesses making better monthly and seasonal decisions regarding crops, logistics, and manning.
* **Loss Reduction:** A measurable decrease in overall losses attributed to weather, geography, and movement inefficiencies.

## Scope and Objectives

### Core Deliverables

**1. Data Aggregation**
* Weather patterns and forecasts.
* Supply chain routing.
* Mobility (Flight and ship paths).
* Approximate population density (Using standard WorldPop data and satellite night light data for visual effects).

**2. Insights Generation**
* Optimal timelines for planting crops.
* Strategic manpower allocation timing.
* Recommendations on which logistics methodology to utilize.
* Typhoon preparation protocols.
* Identification of underutilized or isolated markets.

**3. Web Application**
* Interactive map of the target site and nearby cities.
* Animation of all converging factors (weather, mobility, density).

### Out-of-Scope
* Paid version of data of any kind. Project strictly uses public or free tier data.
* Validation of the data against official census records.
* Guarantees on the absolute accuracy of the generated results.
* Use of LLMs to make autonomous key business decisions.
* Advanced satellite data processing (e.g., SAR - Synthetic Aperture Radar).
* Primary customer interviews.
* Mobile application version.

### Key Dependencies
* Reliable access to satellite data (including night imagery).
* Access to flight and ship path data.
* Access to historical and live weather data APIs.

## Implementation Details

### Technology Stack

* **Frontend:** TypeScript 5 + React 19 on Vite 8, deployed as a fully static bundle. **MapLibre GL JS 6** renders the basemap from self-hosted PMTiles; **deck.gl 9.4** renders every data overlay on WebGL2, attached to the map via `@deck.gl/maplibre`. Data reaches the GPU as binary only: **Apache Arrow 21** buffers handed to deck.gl through its `data: {length, attributes}` binary form. **h3-js 4** provides the aggregation grid, **DuckDB-WASM 1.32** provides in-browser SQL filtering over GeoParquet, and all decode/parse work runs in Web Workers via Comlink. State is Zustand (UI state) plus TanStack Query (artifact fetching); charts are Observable Plot.
* **Backend:** Python 3.13, split into three deliberately separate concerns rather than one service. (1) **Collectors** — single-purpose processes per upstream source; a long-lived `asyncio` WebSocket consumer for AIS, and scheduled pollers for everything else. (2) **Transform** — **DuckDB 1.5** as the analytical engine, with all transformations written as SQL models in `dbt-duckdb`, reading and writing GeoParquet. (3) **Read API** — a thin, stateless **FastAPI** service that exists only for the genuinely dynamic operations (Valhalla routing/isochrone proxying and per-site ad-hoc queries). Everything else is served as pre-baked static artifacts with no backend in the request path.
* **Database & Storage:** Two tiers, chosen because the hot and cold access patterns are irreconcilable. **Hot/operational:** PostgreSQL 18 + **PostGIS 3.6** + **TimescaleDB 2.29** — vessel and aircraft positions land in hypertables partitioned on time, with native compression, continuous aggregates for the rollups the UI actually reads, and retention policies that drop raw positions after 90 days. **Cold/analytical and serving:** S3-compatible object storage (**Cloudflare R2**) holding four artifact formats — **GeoParquet** (analysis and DuckDB-WASM range queries), **PMTiles** (vector basemap and vector overlays, plus raster pyramids for nightlights), **Cloud-Optimized GeoTIFF** (population and nightlight source rasters), and **Arrow IPC** (pre-baked animation frames). The browser reads exclusively from R2.
* **Infrastructure:** **Cloudflare Pages** serves the frontend; **Cloudflare R2** behind a cached custom domain serves every artifact (free egress, and CDN caching keeps tile requests off the Class B operation budget). **GitHub Actions** is the scheduler, ETL runner, and CI — cron workflows drive every poller and the artifact bake. One small **non-hyperscaler VPS** (Hetzner CX22 class, ~€4/month) runs Docker Compose with Postgres, Valhalla, and the AIS collector; it is the project's only recurring cost and it is required for three reasons that no free tier covers: a persistent outbound WebSocket, a routing graph that must stay resident in RAM, and an egress IP that ADS-B and AIS providers do not rate-limit or block the way they block hyperscaler ranges. Routing is **Valhalla** (self-hosted, MIT) over a Geofabrik Philippines OSM extract. Observability is structured JSON logs shipped to the Grafana Cloud free tier.

### Data Sources

Every source below is public or free-tier, per the out-of-scope constraint. Each is reached through exactly one adapter module that owns its credentials, quota, and licence obligations.

| Domain | Primary | Fallback / cross-check | Constraint that shapes the design |
| --- | --- | --- | --- |
| Weather forecast & history | Open-Meteo (`/v1/forecast`, Historical Weather API) | NOAA GFS via NOMADS | Free tier is **non-commercial**, CC-BY 4.0, 600/min · 5k/hr · 10k/day · 300k/month |
| Typhoon tracks (live) | JTWC public products | PAGASA Severe Weather Bulletin parse | No official PAGASA API exists; bulletins are free text and must be parsed defensively |
| Typhoon tracks (historical) | NOAA IBTrACS v04r01 (WP basin subset) | — | Public domain; bulk CSV/NetCDF/Shapefile, ideal for seasonal baselines |
| Ship positions (AIS) | AISStream.io WebSocket | — | Beta, unstable schema, **max 3 connections**, **browser connections forbidden**, drops messages on slow reads |
| Aircraft positions (ADS-B) | adsb.lol `/v2` | OpenSky Network `/states/all` | adsb.lol is ODbL and ~1 req/sec; OpenSky needs OAuth2, is non-commercial, and **may block hyperscaler IPs** |
| Population | WorldPop gridded population | — | Per-country rasters, hundreds of MB; must be clipped before use |
| Nightlights | NASA Black Marble VNP46A3/A4 | WorldPop `ntl_viirs_g2` | Ships as HDF-EOS5, **not** COG; requires an Earthdata token and a conversion step |
| Basemap, roads, ports | OpenStreetMap via Protomaps / Geofabrik PH extract | Overture Maps (places) | ODbL share-alike applies to derived geometry |
| Admin boundaries | PSA/PhilGIS or GADM | — | Boundary vintage must be pinned; PH administrative units change |

### System Architecture

A five-stage, one-directional pipeline. The governing constraint is that **no free-tier upstream API can survive being in the user request path**, so the read path is static-first: the browser fetches immutable, versioned artifacts from a CDN and never contacts a third party.

```
 ┌─ STAGE 1 · INGEST ────────────────────────────────────────────────────┐
 │  One adapter per source. Writes only; never transforms.               │
 │                                                                       │
 │  AISStream (WebSocket, long-lived)  ─┐                                │
 │  adsb.lol / OpenSky (cron 1-5 min)  ─┤                                │
 │  Open-Meteo (cron hourly)           ─┼─>  raw/  landing zone          │
 │  JTWC + PAGASA (cron 3-hourly)      ─┤     (R2, append-only, one      │
 │  IBTrACS / WorldPop / Black Marble  ─┘      object per fetch, keyed   │
 │  (cron monthly, bulk)                       by request hash + time)   │
 └───────────────────────────────────────────────────────────────────────┘
                                 │
 ┌─ STAGE 2 · STORE ─────────────┴───────────────────────────────────────┐
 │  HOT  Postgres 18 + PostGIS + TimescaleDB                             │
 │       hypertables · compression · continuous aggregates · 90d TTL     │
 │       (live positions, recent observations, operational queries)      │
 │                                                                       │
 │  COLD curated/ GeoParquet on R2, written by dbt-duckdb SQL models     │
 │       partitioned by H3 cell + time bucket · schema-versioned         │
 └───────────────────────────────────────────────────────────────────────┘
                                 │
 ┌─ STAGE 3 · INSIGHTS ──────────┴───────────────────────────────────────┐
 │  Deterministic, reproducible, versioned. SQL + NumPy/xarray only.     │
 │  Seasonal windows · route exposure scoring · manning schedules ·      │
 │  market isolation (Valhalla isochrones) · typhoon exposure by H3 cell │
 │  Every output carries inputs, parameters, and a confidence band.      │
 │  No LLM participates in producing a number. (See Out-of-Scope.)       │
 └───────────────────────────────────────────────────────────────────────┘
                                 │
 ┌─ STAGE 4 · BAKE ──────────────┴───────────────────────────────────────┐
 │  The performance boundary. Converts curated data into render-ready    │
 │  artifacts sized to a declared frame budget:                          │
 │    · PMTiles      vector overlays + basemap + nightlight raster       │
 │    · Arrow IPC    decimated, time-indexed trajectory frames           │
 │    · COG          population / nightlight rasters                     │
 │    · GeoParquet   analytical slices for DuckDB-WASM                   │
 │    · insights.json  per-site narrative + numbers                      │
 │  Emits serving/manifest.json: content-hashed URLs, schema version,    │
 │  per-layer observed_at, and freshness state.                          │
 └───────────────────────────────────────────────────────────────────────┘
                                 │
 ┌─ STAGE 5 · SERVE ─────────────┴───────────────────────────────────────┐
 │  Cloudflare CDN ──> browser                                           │
 │    manifest.json ──> Web Worker (fetch + decode) ──> Arrow buffers    │
 │                 ──> deck.gl binary attributes ──> GPU                 │
 │  Dynamic exception, and the only one: FastAPI ──> Valhalla            │
 │  (routing + isochrones, cached, never required for first paint)       │
 └───────────────────────────────────────────────────────────────────────┘
```

**Architectural invariants.** These are load-bearing; violating any one of them collapses a mitigation below.

1. **The browser never calls a third-party API.** Credentials, quotas, and licence obligations live server-side. AISStream explicitly forbids browser connections; treating this as a general rule keeps every other source inside one enforcement point.
2. **Raw data is immutable.** Stage 1 output is append-only and is never edited or deleted. Every later stage is a pure function of `raw/` plus pinned code, so any artifact can be rebuilt from scratch without re-hitting an upstream API.
3. **The read path never depends on upstream liveness.** A failed poll leaves the last good artifact serving, correctly labelled as stale.
4. **Binary end to end.** GeoJSON is an interchange format at source boundaries only. It must not appear between the bake stage and the GPU.
5. **Projections are explicit.** EPSG:4326 for storage and interchange; EPSG:3857 for display only; **H3 (res 5–8) for anything area-normalized**, because the Philippines spans enough latitude that densities computed in 4326 or 3857 are wrong in ways that look plausible.
6. **Time is UTC in storage, Asia/Manila in presentation.** Agricultural and typhoon-preparation decisions are made against the local calendar, so the conversion boundary must be a single, tested layer.
7. **Every rendered number is traceable** to its source artifact, that artifact's `observed_at`, and the pipeline run that produced it.

### Risks and Mitigations

* **Risk:** Processing and animating multiple heavy spatial datasets (mobility paths + weather + nightlights) can cause severe UI lag and browser crashing.
  * **Mitigation:** Move the cost off the client and cap what remains. Nothing is computed at render time that can be computed at bake time. Specifically: (a) mobility animation is served as pre-baked, time-indexed Arrow IPC trajectory frames — Douglas–Peucker simplified at a per-zoom tolerance — and driven by deck.gl `TripsLayer`, so each animation tick updates a uniform rather than re-uploading geometry; (b) declared and enforced frame budget of ≤300k path vertices and ≤500k points per viewport, with the bake stage failing the build if an artifact exceeds it; (c) zoom-gated level of detail — H3 res 4–5 aggregates below zoom 8, individual tracks only at zoom ≥9 and only within the viewport bounding box; (d) nightlights and population render as raster tiles (PMTiles pyramid → `TileLayer`/`BitmapLayer`), never as vector polygons; (e) all fetch, decode, and Arrow assembly happens in Web Workers with zero-copy `ArrayBuffer` transfer, keeping the main thread free for the single `requestAnimationFrame` loop; (f) one animation clock for all layers, so weather, mobility, and density never schedule competing redraws; (g) a device capability probe on load that drops to a static, non-animated mode on low-memory or software-rendered devices, plus an explicit WebGL context-loss handler that rebuilds rather than white-screens; (h) a Playwright performance gate in CI that fails the build on p95 frame time >32 ms or JS heap >800 MB over a scripted pan/zoom/animate session. WebGPU is deliberately excluded until deck.gl ships picking support for it — hover and click are core to the product.
* **Risk:** API rate limits or downtime from weather/flight data dependencies.
  * **Mitigation:** Decouple availability from freshness, and make freshness visible. Because the read path serves static artifacts (invariant 3), an upstream outage degrades data age, not uptime. On top of that: (a) every adapter declares its documented quota and requests pass through a shared token-bucket limiter configured to those numbers (Open-Meteo 600/min · 5k/hr · 10k/day, adsb.lol ~1/sec, OpenSky's per-endpoint credit buckets, AISStream's 3-connection ceiling); (b) every upstream response is written to `raw/` before parsing, so backfills, reprocessing, and tests replay from disk and never re-consume quota — CI is forbidden from touching a live upstream and uses recorded fixtures; (c) two independent providers for each critical domain, with documented failover (weather → Open-Meteo then NOAA GFS; flights → adsb.lol then OpenSky; cyclone tracks → JTWC then PAGASA bulletin parse); (d) retries use exponential backoff with full jitter, honour `Retry-After` and `X-Rate-Limit-*`, never retry a 4xx other than 429, and trip a circuit breaker that parks a source rather than hammering it; (e) AIS has no viable second source, so the design accepts degradation there explicitly — coverage gaps are surfaced, not interpolated over; (f) each layer renders its own `observed_at` and a staleness badge derived from the manifest, and a layer past its freshness threshold is drawn in an unmistakable stale state rather than silently shown as current; (g) pipeline failures alert through GitHub Actions but cannot fail the deployment.
* **Risk:** Licence terms disqualify the free data sources the moment the product is commercial — Open-Meteo's free tier and OpenSky are both non-commercial only, and adsb.lol and OpenStreetMap are ODbL share-alike.
  * **Mitigation:** Treat this as an architectural concern rather than a legal footnote. Each adapter module carries a machine-readable licence and commercial-use flag; a CI check fails if a source is used in a code path marked commercial. Because sources sit behind a uniform adapter interface, swapping Open-Meteo's free endpoint for its paid `customer-api` endpoint is a configuration change, and substituting a commercially licensed AIS or ADS-B feed touches one module. Required attributions are generated from the adapter registry into the UI, so they cannot drift out of date.
* **Risk:** Terrestrial AIS and ADS-B coverage is uneven across an archipelago, and nightlights are attenuated by cloud cover during exactly the typhoon conditions the project cares about. Sparse data looks identical to genuinely low activity, which would produce confidently wrong insights.
  * **Mitigation:** Model coverage as a first-class dimension. Every H3 cell and time bucket stores an observation count and receiver-coverage estimate alongside its value; insight outputs carry a confidence band and are suppressed below a documented observation threshold rather than extrapolated. Black Marble's cloud-cover and quality flags are retained and applied, and nightlight comparisons use monthly (VNP46A3) or annual (VNP46A4) composites instead of daily scenes. The UI distinguishes "no activity" from "no data" visually.
* **Risk:** Free tiers convert to bills without warning — R2 Class B operations, VPS storage growth from AIS ingest, and Actions minutes.
  * **Mitigation:** All tile and artifact traffic is served through a cached Cloudflare custom domain rather than the uncached bucket URL, so cache hits never reach R2. Artifacts are content-hashed with long `Cache-Control` TTLs, making repeat views free. TimescaleDB compression and a 90-day retention policy bound the hot store; anything older lives in GeoParquet at roughly an order of magnitude less space. Bake jobs run on a schedule with concurrency limits, and budget alerts are configured on the Cloudflare account at the outset rather than after the first surprise.

## Milestones

* **Phase 1 (Map Generation and Initial Data Overlay):** Develop the core web app with a free ship and flight path data overlay.
* **Phase 2 (Secondary and Live Data Overlay):** Estimate population additions from WorldPop (with Satellite Nightlight visualization) and overlay live weather data onto the map.
* **Phase 3 (Processing and Insights Generation):** Generate useful business insights from the available data. Ensure insights are configurable per specific site.
* **Phase 4 (Testing & Launch):** Conduct quality assurance, refine rendering performance, execute deployment, and gather initial user feedback.
