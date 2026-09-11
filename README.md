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
* **Any expenditure whatsoever.** Total project cost must be and remain exactly **$0.00** — data, compute, storage, hosting, and domains included. See § Hard Constraint: Zero Cost.
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

### Hard Constraint: Zero Cost

**This project must never generate a charge of any kind. Target spend is $0.00, permanently, with no exceptions and no "it's only a few dollars" line items.** This is a hard architectural constraint of the same standing as correctness, and it takes precedence over performance, convenience, and feature completeness. Where a design choice below looks unusual, this constraint is usually the reason.

Free tiers are not sufficient on their own, because a free tier is a billing account that currently happens to owe nothing — one traffic spike or one forgotten retention policy turns it into an invoice. The design therefore aims a step further: **be structurally incapable of being billed.**

Four rules enforce that:

1. **No payment method on file, anywhere.** This is the single most effective control available. GitHub's documented behaviour is that when an account has no valid payment method, usage is *blocked* once quota is exhausted rather than billed. A hard stop is the desired failure mode; a surprise invoice is not. Any service that requires a card to function is disqualified outright, however generous its free tier.
2. **No service with a metered billing relationship.** This is why Cloudflare R2 was evaluated and rejected despite being the conventional choice for PMTiles hosting: it requires a payment method and bills per-operation past 10 GB and 10 M Class B operations. GitHub Pages and Hugging Face have no billing relationship to exceed — they throttle or refuse, they do not invoice.
3. **No long-running compute.** No VPS, no always-on container, no managed database instance. Every process in this system is an ephemeral job that starts, does work, writes artifacts, and exits. Nothing accrues cost while idle because nothing is idle.
4. **Quotas are treated as build-time budgets, not runtime surprises.** Storage and size ceilings are asserted in CI (see § Risks), so exceeding a free allowance fails a pull request rather than degrading production.

**What this costs in capability, stated honestly.** There is no live view: data is sampled on a schedule rather than streamed continuously, so "live weather" means "refreshed hourly" and vessel tracks are sampled windows rather than complete voyages. Routing answers only pre-computed questions. Total browser-reachable artifact size is capped at 1 GB. These are acceptable because the product's own success metrics are monthly and seasonal decisions, not real-time operations — but they are genuine limitations and the UI must not imply otherwise.

An earlier revision of this document specified a ~€4/month VPS to host a persistent AIS WebSocket, a resident Valhalla routing graph, and the API. That is removed. Sampling AIS inside scheduled jobs, building the Valhalla graph inside the bake job, and pushing query execution into the browser via DuckDB-WASM together cover the same ground at zero cost, and as a side effect eliminate every server, database, and API from the system.

### Technology Stack

* **Frontend:** TypeScript 5 + React 19 on Vite 8, deployed as a fully static bundle. **MapLibre GL JS 6** renders the basemap from self-hosted PMTiles; **deck.gl 9.4** renders every data overlay on WebGL2, attached to the map via `@deck.gl/maplibre`. Data reaches the GPU as binary only: **Apache Arrow 21** buffers handed to deck.gl through its `data: {length, attributes}` binary form. **h3-js 4** provides the aggregation grid and all decode/parse work runs in Web Workers via Comlink. **DuckDB-WASM 1.32** is load-bearing rather than a convenience: it range-queries GeoParquet over HTTP directly from the browser, which is what allows the system to have no query backend at all. State is Zustand (UI state) plus TanStack Query (artifact fetching); charts are Observable Plot.
* **Compute (there is no backend):** Python 3.13 running **exclusively inside ephemeral GitHub Actions jobs**. No server, no container, no process outlives the job that started it. Three job families: (1) **collectors**, one per upstream source, which fetch and write raw responses and nothing else — AIS is a bounded sampling window against the AISStream WebSocket rather than a persistent consumer; (2) **transforms**, written as SQL models in `dbt-duckdb`; (3) **bake**, which produces render-ready artifacts and publishes them. **DuckDB 1.5** is the entire engine, with the `spatial` (ST_* predicates and geometry I/O), `h3` (community), and `httpfs` extensions loaded — verified to cover the spatial and time-bucketing work that previously justified a database server. **Valhalla** runs as a throwaway container *inside* the bake job: build the graph from a Geofabrik Philippines extract, answer the route/isochrone questions the insights need, emit the results as artifacts, discard the graph.
* **Database & Storage:** **No database server.** GeoParquet on object storage is the database and DuckDB is the engine — a decision the batch, monthly/seasonal access pattern permits and the zero-cost constraint requires. Four artifact formats: **GeoParquet** (analysis, and browser range-queries via DuckDB-WASM), **PMTiles** (vector basemap and overlays, plus raster pyramids for nightlights), **Cloud-Optimized GeoTIFF** (population and nightlight source rasters), and **Arrow IPC** (pre-baked animation frames). Two hosts, chosen because both were empirically confirmed to return `206 Partial Content` with working CORS, which PMTiles and Parquet range reads require: **GitHub Pages** for the browser-facing serving set (hard 1 GB ceiling; published via `upload-pages-artifact`/`deploy-pages` so artifacts never enter git history and never bloat the repository), and a **Hugging Face Dataset** repository for the raw landing zone and long-horizon history, which is versioned, far more capacious, and range-readable by the browser directly. GitHub Releases was tested and rejected: range requests work, but it sends no `Access-Control-Allow-Origin` header and its URLs are short-lived signed redirects, so browsers cannot read it.
* **Infrastructure:** Three accounts, none of which has a payment method attached. **GitHub Actions** on a public repository is the scheduler, ETL runner, and CI — free and unlimited on standard runners, and hard-blocked rather than billed when quota is exhausted. **GitHub Pages** serves the application and the serving set over its CDN. **Hugging Face** holds the data archive. There is no VPS, no Kubernetes, no managed database, no CDN contract, and no custom domain. Observability is the Actions run log plus a `pipeline_health.json` artifact that the UI reads and displays, because log aggregation services meter and therefore bill.

### Data Sources

Every source below is free at the point of use and requires no payment method, per § Hard Constraint: Zero Cost. Each is reached through exactly one adapter module that owns its credentials, quota, and licence obligations.

| Domain | Primary | Fallback / cross-check | Constraint that shapes the design |
| --- | --- | --- | --- |
| Weather forecast & history | Open-Meteo (`/v1/forecast`, Historical Weather API) | NOAA GFS via NOMADS | Free tier is **non-commercial**, CC-BY 4.0, 600/min · 5k/hr · 10k/day · 300k/month |
| Typhoon tracks (live) | JTWC public products | PAGASA Severe Weather Bulletin parse | No official PAGASA API exists; bulletins are free text and must be parsed defensively |
| Typhoon tracks (historical) | NOAA IBTrACS v04r01 (WP basin subset) | — | Public domain; bulk CSV/NetCDF/Shapefile, ideal for seasonal baselines |
| Ship positions (AIS) | AISStream.io WebSocket | — | Beta, unstable schema, **max 3 connections**, **browser connections forbidden**, drops messages on slow reads; consumed as bounded sampling windows since no persistent process is affordable |
| Aircraft positions (ADS-B) | adsb.lol `/v2` | OpenSky Network `/states/all` | adsb.lol is ODbL and ~1 req/sec; OpenSky needs OAuth2, is non-commercial, and **may block hyperscaler IPs** |
| Population | WorldPop gridded population | — | Per-country rasters, hundreds of MB; must be clipped before use |
| Nightlights | NASA Black Marble VNP46A3/A4 | WorldPop `ntl_viirs_g2` | Ships as HDF-EOS5, **not** COG; requires an Earthdata token and a conversion step |
| Basemap, roads, ports | OpenStreetMap via Protomaps / Geofabrik PH extract | Overture Maps (places) | ODbL share-alike applies to derived geometry |
| Admin boundaries | PSA/PhilGIS or GADM | — | Boundary vintage must be pinned; PH administrative units change |

### System Architecture

A five-stage, one-directional batch pipeline with **no server, no database, and no API anywhere in it**. Two constraints converge on the same shape. First, no free-tier upstream API can survive being in the user request path. Second, nothing may cost money, which rules out anything long-lived. Both are satisfied by making the read path entirely static: the browser fetches immutable, content-hashed artifacts from a CDN, queries them in place with DuckDB-WASM, and never contacts a third party or an origin server.

Stages 1 through 4 exist only while a scheduled job is running. Stage 5 is a set of files.

```
 ┌─ STAGE 1 · COLLECT ───────────────────────────────────────────────────┐
 │  Scheduled GitHub Actions jobs. One per source. Fetches and           │
 │  writes; never transforms. Nothing here is long-lived.                │
 │                                                                       │
 │  AISStream   bounded sampling window, not a live feed  ─┐             │
 │  adsb.lol    cron, viewport-scoped                     ─┤             │
 │  Open-Meteo  cron hourly                               ─┼─>  raw/     │
 │  JTWC/PAGASA cron 3-hourly, bulletin text              ─┤    on HF    │
 │  IBTrACS / WorldPop / Black Marble   cron monthly      ─┘    dataset  │
 │                                                                       │
 │  Append-only. One object per fetch, keyed by request hash + time.     │
 └───────────────────────────────────────────────────────────────────────┘
                                 │
 ┌─ STAGE 2 · STORE ─────────────┴───────────────────────────────────────┐
 │  No database server. GeoParquet is the store, DuckDB is the engine.   │
 │                                                                       │
 │  DuckDB 1.5 + spatial + h3 + httpfs, inside the job:                  │
 │    raw/  ─>  curated/  GeoParquet, partitioned by H3 cell + time      │
 │                          bucket, schema-versioned, compacted          │
 │                                                                       │
 │  Transforms are dbt-duckdb SQL models. Nothing runs between jobs.     │
 └───────────────────────────────────────────────────────────────────────┘
                                 │
 ┌─ STAGE 3 · INSIGHTS ──────────┴───────────────────────────────────────┐
 │  Deterministic, reproducible, versioned. SQL + NumPy/xarray only.     │
 │  Seasonal windows · route exposure scoring · manning schedules ·      │
 │  typhoon exposure by H3 cell · market isolation, using a Valhalla     │
 │  graph built and discarded inside this job.                           │
 │                                                                       │
 │  Every output carries inputs, parameters, and a confidence band.      │
 │  No LLM participates in producing a number. (See Out-of-Scope.)       │
 └───────────────────────────────────────────────────────────────────────┘
                                 │
 ┌─ STAGE 4 · BAKE ──────────────┴───────────────────────────────────────┐
 │  The performance and budget boundary. Converts curated data into      │
 │  render-ready artifacts sized to declared, CI-asserted limits:        │
 │    · PMTiles      vector overlays + basemap + nightlight raster       │
 │    · Arrow IPC    decimated, time-indexed trajectory frames           │
 │    · COG          population / nightlight rasters                     │
 │    · GeoParquet   analytical slices for DuckDB-WASM                   │
 │    · insights.json + pipeline_health.json                             │
 │                                                                       │
 │  Emits serving/manifest.json: content-hashed URLs, schema version,    │
 │  per-layer observed_at, freshness state. Fails the build if the       │
 │  serving set exceeds 1 GB or a frame budget is breached.              │
 └───────────────────────────────────────────────────────────────────────┘
                                 │
 ┌─ STAGE 5 · SERVE ─────────────┴───────────────────────────────────────┐
 │  Static only. No API, no origin server, no query backend.             │
 │                                                                       │
 │  GitHub Pages CDN  (serving set, ≤1 GB)   ─┬─>  browser               │
 │  Hugging Face      (history, range-read)  ─┘                          │
 │                                                                       │
 │    manifest.json ─> Web Worker (fetch + decode) ─> Arrow buffers      │
 │                  ─> deck.gl binary attributes ─> GPU                  │
 │                                                                       │
 │  Ad-hoc filtering and aggregation run in DuckDB-WASM against          │
 │  GeoParquet over HTTP range requests, so nothing in the request       │
 │  path can bill, throttle, or go down.                                 │
 └───────────────────────────────────────────────────────────────────────┘
```

**Architectural invariants.** These are load-bearing; violating any one of them collapses a mitigation below. Invariant 0 outranks the rest.

0. **Nothing may incur a charge.** No payment method, no metered service, no idle compute. A design that cannot be delivered at $0.00 is not delivered. See § Hard Constraint: Zero Cost.
1. **The browser never calls a third-party API.** Credentials, quotas, and licence obligations live inside the collector jobs. AISStream explicitly forbids browser connections; treating this as a general rule keeps every other source inside one enforcement point.
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
* **Risk:** The project incurs a charge — the outcome the zero-cost constraint exists to prevent. The realistic mechanisms are a free tier silently converting to metered billing, a service quietly requiring a card, storage creeping past an allowance, or a runaway job.
  * **Mitigation:** Remove the billing relationship rather than manage it, and make overage a build failure. Specifically: (a) no payment method is attached to any account used by this project, so GitHub's documented behaviour is to block on quota exhaustion instead of invoicing — a hard stop is the intended failure mode; (b) only GitHub Actions, GitHub Pages, and Hugging Face are used, none of which can produce an invoice for this workload, and Cloudflare R2 was rejected specifically because it requires a card and meters per-operation; (c) nothing runs between jobs, so there is no idle cost to forget about; (d) size and quota ceilings are asserted in CI — the bake job fails if the serving set exceeds 1 GB, and a retention-and-compaction step bounds the archive, so an overrun breaks a pull request rather than production; (e) collector jobs declare `timeout-minutes` and `concurrency` groups so a hung job cannot spin; (f) larger GitHub-hosted runners are always billable even on public repositories and are therefore prohibited outright — standard runners only; (g) no custom domain, since domains are the one component with no free tier at all.
* **Risk:** Licence terms disqualify the free data sources the moment the product is commercial — Open-Meteo's free tier and OpenSky are both non-commercial only, and adsb.lol and OpenStreetMap are ODbL share-alike.
  * **Mitigation:** Treat this as an architectural concern rather than a legal footnote. Each source adapter carries a machine-readable licence and commercial-use flag; a CI check fails if a source is used in a code path marked commercial. Required attributions are generated from that registry into the UI, so they cannot drift out of date. Note the direct tension with the zero-cost constraint: the escape hatch for commercial use is Open-Meteo's paid `customer-api` endpoint and a licensed AIS or ADS-B feed, which by definition ends the $0.00 guarantee. The architecture keeps that swap cheap in engineering terms — one module per source — but it must be a deliberate decision to start spending, never an accident. Until then, the project is non-commercial, and the UI must not be placed behind a subscription or carry advertising, either of which would breach Open-Meteo's terms on its own.
* **Risk:** Terrestrial AIS and ADS-B coverage is uneven across an archipelago, and nightlights are attenuated by cloud cover during exactly the typhoon conditions the project cares about. Sparse data looks identical to genuinely low activity, which would produce confidently wrong insights. **Zero-cost collection makes this materially worse:** without a persistent consumer, AIS arrives as periodic sampling windows, so an absent vessel may simply have moved between samples.
  * **Mitigation:** Model coverage as a first-class dimension rather than assuming completeness. Every H3 cell and time bucket stores an observation count, a sampled-duration fraction, and a receiver-coverage estimate alongside its value. Insights are computed only over windows whose sampled fraction exceeds a documented threshold, carry a confidence band, and are suppressed rather than extrapolated below it. Because the product reasons in months and seasons, sampling is statistically adequate for route-frequency and port-activity measures provided sample windows are scheduled at varying times of day to avoid aliasing against tidal, shift, and diurnal patterns — a fixed hourly offset would bias every measure. Vessel tracks are presented explicitly as sampled positions, never interpolated into continuous voyages. Black Marble cloud-cover and quality flags are retained and applied, and nightlight comparisons use monthly (VNP46A3) or annual (VNP46A4) composites instead of daily scenes. The UI distinguishes "no activity" from "no data" visually.
* **Risk:** The free platform itself changes the rules. Concretely: scheduled workflows in a public repository are automatically disabled after 60 days without repository activity, which would silently stop all data collection; GitHub Actions runners are Azure-hosted, and OpenSky documents that it may block hyperscaler IP ranges; and GitHub Pages' 1 GB site ceiling is a hard wall, not a soft one.
  * **Mitigation:** Each of these is a known failure mode with a specific countermeasure. A weekly keepalive job calls `gh workflow enable` on every scheduled workflow, which resets the 60-day inactivity timer without needing a commit, and the freshness badge in the UI surfaces a stalled pipeline within one cycle. adsb.lol is the primary flight source precisely because it publishes no hyperscaler restriction; OpenSky is treated as an optional cross-check whose loss degrades confidence rather than breaking a layer, and if it blocks the runner the collector records that as a source outage instead of retrying. The 1 GB ceiling is enforced at bake time with headroom, and the archive-versus-serving split exists so growth lands in Hugging Face — where capacity is generous — rather than against the Pages limit. Because the whole platform choice is a risk concentration, artifact formats were deliberately kept host-agnostic: PMTiles, GeoParquet, COG, and Arrow IPC need only HTTP range requests and CORS, so relocating to another free static host is a URL change in the manifest.

## Milestones

* **Phase 1 (Map Generation and Initial Data Overlay):** Develop the core web app with a free ship and flight path data overlay.
* **Phase 2 (Secondary and Live Data Overlay):** Estimate population additions from WorldPop (with Satellite Nightlight visualization) and overlay live weather data onto the map.
* **Phase 3 (Processing and Insights Generation):** Generate useful business insights from the available data. Ensure insights are configurable per specific site.
* **Phase 4 (Testing & Launch):** Conduct quality assurance, refine rendering performance, execute deployment, and gather initial user feedback.
