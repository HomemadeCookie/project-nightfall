# Nightfall — Architecture & Build Plan

> Clean-slate design. This document supersedes every other `.md` in the old
> implementation. It is the spec the new branch is built from.

Nightfall turns free public data (ships, flights, satellites, weather, text,
prices) into **answers to specific, paid-for business questions about the
Philippine supply chain**. It serves two kinds of customer: companies that move goods,
and the sari-sari stores at the end of the chain.

Hard constraint: **₱0 running cost.** Every component below has a free path.

---

## 1. Commercial model

Data is not the product. Answers that change a decision are. Each question in §2
names the decision it changes and who pays for that.

| Segment | Examples | What they buy | How |
|---|---|---|---|
| **Importers & traders** | rice/sugar/flour importers, fuel retailers, FMCG importers | port wait, staple import pipeline, upstream disruption | B2B subscription, API/CSV export |
| **Logistics** | forwarders, truckers, inter-island shippers, 3PLs | port wait, ferry suspension, flood access, fuel price | B2B subscription, alerts |
| **Distributors & B2B retail platforms** | FMCG distributors, sari-sari B2B ordering apps | regional stock-up / stockout risk, price direction | Data feed + white-label advisories pushed to their store networks |
| **FMCG brands** | consumer goods makers | where and when demand surges or supply drops, by region | Regional risk index subscription |
| **Lenders & insurers** | MSME lenders, microfinance, parametric insurers | typhoon exposure, regional disruption history | Data licence |
| **Sari-sari stores** | individual owners | "Should I stock up? Will prices rise?" | **Free** via chatbot, paid for by distributors, brands and lenders who want that channel and the aggregate data |

Implications for design:

- **Use only sources whose licence allows commercial use** in anything that gets
  published (§6). Non-commercial sources can be used for research inside `eval/`
  and nowhere else.
- **Every answer must be backtested and beat a naive baseline** before it ships.
  A paying customer will check.
- **Outputs come in three forms:** plain-language verdicts (stores), dashboards
  (analysts), CSV/Parquet/API (integrations).

---

## 2. The questions

Geographic scope: the Philippines, plus the shipping lanes and origin
ports that feed it (Vietnam, Thailand, China, Singapore/Malacca, Taiwan Strait).

### 2.1 Summary

| ID | Question | Primary buyer | Horizon | Tier |
|---|---|---|---|---|
| `fuel.next_week` | How much will pump prices change next Tuesday? | everyone (fleets, transport, retail) | 1 week | **1** |
| `ports.wait` | How long will a vessel wait at port X this week? | importers, forwarders | 0–14 d | **1** |
| `ferry.suspension` | Will RoRo route X be suspended, and for how long? | inter-island logistics, distributors | 0–5 d | **1** |
| `staples.import_pipeline` | How much rice / wheat / sugar / fuel is arriving in the next 30 days vs. normal? | traders, millers, distributors | 0–30 d | **1** |
| `staples.price_direction` | Will the price of staple X in region Y rise over the next 2–4 weeks? | distributors, retailers, brands | 2–4 wk | **1** |
| `retail.stock_up` | Should I stock up on item X this week? (store-level) | stores (paid for by distributors) | 1 wk | **1** |
| `lanes.upstream_disruption` | Will a disruption upstream reach PH inbound capacity, and when? | procurement, planners | 2–6 wk | 2 |
| `typhoon.asset_exposure` | Which of *my* sites and routes will a storm hit, and for how long? | corporates, insurers | 0–5 d | 2 |
| `lastmile.flood_access` | Which delivery areas are flooded or unreachable now? | distributors, e-commerce, insurers | now | 2 |
| `suppliers.activity` | Is activity in my supplier region normal? | importers, procurement | weekly | 3 |
| `aircargo.capacity` | Is air cargo capacity into MNL/CEB/CRK tightening? | electronics exporters, forwarders | weekly | 3 |

Tier 1 = the MVP product. Tier 2 = premium B2B. Tier 3 = adds detail to Tier 1 and 2.

### 2.2 Question specs

Each question becomes a YAML spec in `questions/` (format in §8.3). Each entry
below is the design input for that spec.

---

#### `fuel.next_week` — next Tuesday's pump price adjustment

- **Decision it changes:** fleet operators and stores time their fuel and LPG
  purchases. Transport groups plan around it. Retail prices of many goods
  follow it.
- **Why it sells:** weekly, national, and easy to understand. It is a strong
  free hook that builds trust in the paid products.
- **Output:** for diesel, gasoline and kerosene, a ₱/L change with a range and
  a direction. Published Friday evening Manila time, ahead of the Tuesday adjustment.
- **Inputs:** daily crude benchmarks (EIA, public domain), PHP/USD (BSP), and
  industry estimates reported in the news (text) as an extra feature.
- **Method v1:** the DOE adjustment follows the average Mon–Fri change in
  regional product prices from the previous week. Regional prices (MOPS) are
  paywalled, so model the adjustment from crude change × FX with a fitted
  regression on past adjustments.
- **Ground truth:** official DOE/oil company adjustments, collected from DOE
  pages and news.
- **Metric:** direction accuracy and MAE in ₱/L. **Baselines:** last week's
  change, and zero.
- **Ship when:** direction accuracy ≥ 80% and MAE beats both baselines over
  52 backtested weeks.

---

#### `ports.wait` — port congestion and expected wait

- **Ports:** Manila (MICT, South Harbor, North Harbor), Batangas, Subic, Cebu,
  Davao, Cagayan de Oro, General Santos, Iloilo.
- **Decision it changes:** when to book trucks, whether to reroute
  (Manila → Batangas/Subic), and how to avoid demurrage and detention charges.
- **Output:** per port and day, vessels at anchor, median and p90 time at
  anchor, median time at berth, congestion index (z-score vs. 90-day norm),
  and a 7- and 14-day outlook.
- **Inputs:** AIS positions (anchorage/berth geofences), IMF PortWatch port
  calls, weather (berthing stoppages), typhoon tracks.
- **Method v1:** segment port calls from AIS (anchorage → berth → depart).
  Forecast with seasonal baseline + current queue + storm adjustment.
- **Ground truth:** wait times we measure from AIS after the fact, and monthly
  PPA port statistics.
- **Metric:** MAE in hours for anchorage wait. **Baseline:** trailing 4-week
  median.
- **Known gap:** free terrestrial AIS coverage varies by port. Publish a
  coverage score per port and suppress answers where it is too low.

---

#### `ferry.suspension` — inter-island RoRo sailing suspension

- **Routes (v1):** Batangas–Calapan, Matnog–Allen, Liloan–Lipata,
  Cebu–Tagbilaran, Cebu–Ormoc, Iloilo–Bacolod, Dumangas–Bacolod, Dapitan–Dumaguete.
  These carry most of the trucked goods between islands.
- **Decision it changes:** whether to dispatch trucks now, hold them, or
  reroute. Whether stores on affected islands should restock before the
  suspension. Trucks stranded at Matnog in every major storm show what this costs.
- **Output:** for each route, the probability of suspension in 24 / 48 / 72 / 120 h,
  the expected duration, and an estimate of truck backlog when one is available.
- **Inputs:** storm forecast tracks (JTWC/GDACS), PAGASA wind signals, forecast
  wind and waves (ECMWF open data, NOAA WaveWatch III), AIS activity of ferry
  vessels, Coast Guard (PCG) advisories (text).
- **Method v1:** suspension follows PAGASA wind signal levels and forecast sea
  state along each route. Start with a logistic model on forecast wind and wave
  height at route waypoints plus the forecast signal level.
- **Ground truth:** PCG advisories, plus ferry AIS going quiet (no sailings in a
  window where some are scheduled).
- **Metric:** Brier score and recall at 48 h. **Baseline:** "suspended if
  signal ≥ 1 is forecast for either port".

---

#### `staples.import_pipeline` — what is about to arrive

- **Commodities:** rice, wheat (flour), sugar, refined fuel/LPG, soybean meal (feed).
- **Decision it changes:** whether traders buy forward or wait, whether millers
  and distributors build inventory, and how to price against an incoming
  glut or shortage. The Philippines is one of the world's largest rice importers.
- **Output:** expected arrivals per commodity and port over the next 30 days
  (vessel count and estimated tonnage) vs. the seasonal norm, with a list of
  vessels and their ETAs.
- **Inputs:** AIS (vessel type, draught, destination field, voyage history),
  PortWatch, reference list of origin ports (rice: Vietnam and Thailand
  loading ports; wheat: US, Australia, Canada and Black Sea loading ports; etc.).
- **Method v1:** match each voyage to a commodity with rules on vessel type,
  origin port and draught (loaded vs. ballast) to get P(commodity | voyage).
  Estimate tonnage from deadweight and draught change.
- **Ground truth:** realised arrivals (AIS), PSA/BOC monthly import statistics,
  rice import arrival reports in the news.
- **Metric:** MAPE on monthly arrivals per commodity vs. PSA. **Baseline:**
  same month last year.
- **Honest limitation:** commodity attribution is probabilistic. Always show
  confidence.

---

#### `staples.price_direction` — will it get more expensive?

- **Items:** rice (regular/well-milled), sugar, cooking oil, flour, onion,
  garlic, eggs, canned sardines, instant noodles, LPG (11 kg), diesel.
- **Decision it changes:** buying ahead or holding off, for distributors,
  retailers and stores.
- **Output:** for each item and region (PSGC region), a direction (up / flat / down)
  over 2 and 4 weeks, a probability, and the main drivers.
- **Inputs:** DA price monitoring, PSA retail prices, `fuel.next_week`,
  `staples.import_pipeline`, typhoon exposure, `ferry.suspension` (island
  regions), world commodity prices (World Bank Pink Sheet), FX, text events
  (import bans, SRP changes, tariff changes).
- **Method v1:** gradient-boosted classifier on lagged features. Validate
  walk-forward, never with a random split.
- **Metric:** balanced accuracy of direction. **Baseline:** persistence
  ("same direction as the last 2 weeks").
- **Ship rule:** only publish items and regions where the model beats
  persistence in backtest. Everything else stays hidden.

---

#### `retail.stock_up` — store-level advisory

- **Who:** a sari-sari store owner, via Messenger or Telegram, in Filipino or English.
- **Decision it changes:** how much to restock this week, given limited cash.
- **Output:** for the store's region, a short list of
  `{item, verdict: stock_up | normal | wait, reason}`. For example:
  *"Bumili na ng bigas at de-lata ngayong linggo — may bagyo at posibleng
  suspendido ang biyahe sa Matnog simula Huwebes."*
- **Inputs:** combines `staples.price_direction`, `fuel.next_week`,
  `ferry.suspension`, typhoon exposure, and storm-driven demand (candles,
  batteries, water, canned goods, noodles).
- **Method v1:** clear rules over the upstream answers. No new model.
- **Commercial angle:** distributors and B2B ordering platforms white-label
  this for their store networks. The anonymised aggregate (which items, which
  regions, when) is a sellable demand signal for brands.
- **Metric:** whether the upstream answers came true, plus feedback (👍/👎)
  from users.

---

#### `lanes.upstream_disruption` — trouble upstream, arriving later

- **Watch list:** Malacca/Singapore Strait, Taiwan Strait, South China Sea
  lanes, Chinese and Vietnamese origin ports, Red Sea/Suez (global effects on
  freight rates and capacity).
- **Output:** a disruption score per chokepoint or origin port (transits vs.
  norm) with the expected lag to PH arrivals.
- **Inputs:** PortWatch chokepoint transits and port calls, AIS where
  coverage allows, text events (GDELT).
- **Metric:** whether flagged disruptions are followed by lower PH arrivals
  within the predicted lag.

#### `typhoon.asset_exposure` — my sites and routes

- **Premium B2B product.** Customers upload sites (warehouses, stores,
  suppliers) and routes.
- **Output:** forecast wind swath and rainfall per site, expected downtime,
  and which routes are cut (from `ferry.suspension` and `lastmile.flood_access`).
- **Inputs:** storm tracks, ECMWF/GFS forecast fields, history of past storms
  (IBTrACS) for calibration.

#### `lastmile.flood_access` — where trucks can't go

- **Output:** flood extent polygons (Sentinel-1 radar change detection) and the
  barangays or roads affected, after heavy rain.
- **Inputs:** Sentinel-1 GRD (Copernicus), rainfall, OSM roads,
  PSGC boundaries, text reports.
- **Limitation:** Sentinel-1 revisits every 6–12 days. Fill the gaps with
  rainfall-based flood likelihood and text reports, and label each result by
  where it came from.

#### `suppliers.activity` — supplier-region pulse

- **Output:** weekly activity index per supplier region, from Sentinel-5P NO₂
  (industrial activity), VIIRS night lights, and port throughput (PortWatch).
- **Metric:** correlation with official industrial production releases.

#### `aircargo.capacity` — air freight into PH

- **Output:** weekly cargo-operator movements and widebody flights into
  MNL/CEB/CRK vs. norm.
- **Inputs:** adsb.lol (ODbL), filtered to cargo airline codes and aircraft types.

---

## 3. Design principles

1. **Start from the questions.** A source, model or table exists only because
   a question spec lists it as an input. `nightfall lineage <question>` must
   be able to trace any answer back to raw records.
2. **Process in batch and publish static files.** No always-on database or API
   server. Results are baked to Parquet, PMTiles and JSON on object storage.
   Browsers query them with DuckDB-WASM.
3. **Keep raw data unchanged and record its origin.** Every raw record sits in
   an envelope with source, licence, fetch time and payload hash. Every
   derived layer can be rebuilt from raw.
4. **Time travel.** Every table records both event time and the time we knew
   about it. Backtests use only data known before the forecast was made
   (`known_at <= as_of`), so no future data leaks in.
5. **One spatial model.** Join on H3 cells (res 7 for regional work, res 9
   for ports and anchorages) plus named geofences. Never join on raw coordinates.
6. **Answers come with confidence and evidence.** Every answer has a
   verdict, a probability or range, a coverage score and evidence links.
   Low coverage means no answer, not a guess.
7. **Prove it before shipping it.** Every question has a backtest and a
   baseline it must beat, both versioned in `eval/`.
8. **Licences are enforced in code.** Publish fails if any input to an output
   has a licence that forbids commercial use.
9. **Each source is a separate plug-in.** Adding a source means adding one
   adapter and one dbt staging model. The core never changes for it.

---

## 4. Architecture

```
 SOURCES             INGEST                  LAKE (Parquet on R2, Hive-partitioned)        SERVE
┌───────────┐   ┌───────────────────┐   ┌────────────────────────────────────────────┐   ┌─────────────────┐
│ ships     │──▶│ batch adapters     │──▶│ raw/         envelopes, immutable          │   │ publish/        │
│ flights   │   │ (GitHub Actions    │   │ staging/     typed, deduped, UTC           │   │  answers/*.json │──▶ web (static + DuckDB-WASM)
│ satellite │   │  cron)             │   │ entities/    vessel, port, route, region…  │──▶│  tables/*.parq  │──▶ bot (CF Worker → Messenger/Telegram)
│ weather   │──▶│                    │   │ events/      port_call, sailing, storm…    │   │  tiles/*.pmtiles│──▶ B2B feeds (CSV/Parquet URLs)
│ text      │   │ stream collector   │   │ features/    model inputs, as-of safe      │   │  manifest.json  │
│ markets   │──▶│ (free VM: AIS ws)  │   │ indicators/  time series per entity/cell   │   └─────────────────┘
└───────────┘   └───────────────────┘   │ answers/     question × scope × as_of      │
                                         └────────────────────────────────────────────┘
                                              ▲                │
                                         reference/        eval/ (backtests, baselines, reports)
```

### 4.1 Layers

| Layer | Built by | Contents |
|---|---|---|
| `raw` | `sources/*` adapters | Envelope + original payload. Partitioned `source=/date=/hour=`. Never rewritten. |
| `staging` | dbt | One table per source. Typed, deduplicated, UTC, invalid rows dropped. |
| `entities` | dbt + Python | Stable IDs: `vessel`, `aircraft`, `port`, `berth_zone`, `anchorage`, `route`, `ferry_route`, `commodity`, `region`, `site` (customer). |
| `events` | Python `detect/` | `port_call`, `anchorage_wait`, `ferry_sailing`, `voyage`, `storm_forecast`, `storm_signal`, `flood_extent`, `advisory`, `price_obs`, `fuel_adjustment`. |
| `features` | dbt + Python | Model-ready, keyed `(entity, as_of)`, only data known at `as_of`. |
| `indicators` | Python `indicators/` | Time series: congestion index, ferry activity, import pipeline, disruption scores. |
| `answers` | Python `answers/` | One row per `(question_id, scope, as_of)` following the answer contract (§8.2). |

### 4.2 Runtime split

| Workload | Where it runs | Why |
|---|---|---|
| Batch ingest (hourly/daily) | GitHub Actions cron | Free and unlimited on a public repo |
| AIS websocket | Oracle Cloud Always Free ARM VM (systemd) | Needs a long-lived connection. Writes hourly Parquet to R2. |
| dbt + detect + indicators + answers + publish | GitHub Actions, DuckDB | Data fits on one machine |
| Local LLM for text extraction | Same Oracle VM (Ollama, small quantised model) | Free and private; batch speed is enough |
| Static site | Cloudflare Pages | Free |
| Bot webhook, store subscriptions | Cloudflare Workers + D1 (free tier) | Low traffic, serverless |
| Hot storage | Cloudflare R2 (≤10 GB free, no egress fees) | Serves the lake to the browser and to Actions |
| Cold archive | Hugging Face Datasets | Free, versioned. Raw data older than 90 days goes here. |

---

## 5. Cadences

| Job | Cadence | Feeds |
|---|---|---|
| AIS collector | continuous → hourly flush | ports, ferries, imports |
| PortWatch | daily | ports, imports, upstream |
| Storm tracks (GDACS/JTWC) and PAGASA signals | every 3 h (hourly when a storm is in the PH area) | ferry, typhoon, stock-up |
| ECMWF/GFS forecast fields | every 6 h | ferry, typhoon |
| EIA crude, BSP FX | daily | fuel |
| DOE adjustments (text/news) | daily, more often Mon–Tue | fuel ground truth |
| DA/PSA prices | daily/weekly per source | price direction |
| GDELT + RSS + gov advisories | hourly | all (evidence, events) |
| Sentinel-1 search + flood job | daily; on demand after heavy rain | flood access |
| Sentinel-5P / night lights | weekly | supplier activity |
| adsb.lol | hourly snapshot | air cargo |
| Full build → publish | hourly (light), daily (full) | everything |
| Backtests | weekly + on every model change (CI) | eval reports |

---

## 6. Data sources and commercial-use licensing

Status: ✅ commercial use OK · ⚠️ check the terms before commercial launch ·
❌ non-commercial only (allowed in `eval/` only, never published).

| Source | Domain | Licence status | Notes |
|---|---|---|---|
| ECMWF Open Data | weather | ✅ CC BY 4.0 | forecast fields; attribution required |
| NOAA GFS, WaveWatch III | weather | ✅ US public domain | |
| JTWC | storms | ✅ US public domain | |
| GDACS | storms | ⚠️ | |
| PAGASA bulletins | storms | ⚠️ PH gov | scraped |
| Open-Meteo (free API) | weather | ❌ free tier is non-commercial | use ECMWF/GFS directly instead |
| IBTrACS | storm history | ✅ NOAA | calibration |
| AISStream.io | ships | ⚠️ | main live AIS |
| IMF PortWatch | ships/ports | ⚠️ (believed open with attribution) | port calls, chokepoint transits |
| Global Fishing Watch | ships | ❌ | research only |
| adsb.lol | flights | ✅ ODbL | attribution; share-alike on derived databases |
| OpenSky | flights | ❌ | research only |
| Copernicus Sentinel-1/2/5P | satellite | ✅ free, incl. commercial | via Copernicus Data Space |
| NASA FIRMS, Black Marble | satellite | ✅ NASA open data | |
| EIA | energy prices | ✅ US public domain | |
| World Bank Pink Sheet | commodities | ✅ CC BY 4.0 | |
| BSP | FX | ⚠️ PH gov | |
| DA price monitoring, PSA OpenSTAT, DOE | prices | ⚠️ PH gov | scraped PDFs/HTML |
| GDELT | text | ✅ free, attribution | |
| News RSS | text | ⚠️ | keep extracted facts and links only, never republish article text |
| PCG / MARINA / PPA advisories | text | ⚠️ PH gov | |
| OpenStreetMap | roads, ports | ✅ ODbL | |
| PSGC | admin boundaries | ✅ PH gov open data | |

Every adapter declares its licence in code (`License.COMMERCIAL_OK |
ATTRIBUTION | SHARE_ALIKE | NON_COMMERCIAL`). Licences propagate through
lineage, and `publish` refuses any output with a `NON_COMMERCIAL` input.
Attributions are collected into `manifest.json` and shown in the UI.

---

## 7. Infrastructure (₱0)

| Need | Choice | Free-tier limit to watch |
|---|---|---|
| CI + batch | GitHub Actions | Repo must stay public for unlimited minutes; job time limit 6 h |
| Long-running compute | Oracle Cloud Always Free (Ampere A1) | Idle VMs can be reclaimed; keep collector running and health-checked |
| Object storage | Cloudflare R2 | 10 GB storage, 1M writes/mo, 10M reads/mo |
| Archive | Hugging Face Datasets | Keep repos tidy; Parquet only |
| Site | Cloudflare Pages | 500 builds/mo |
| Serverless + small DB | Cloudflare Workers + D1 | 100k requests/day |
| Messaging | Telegram Bot API, Messenger Platform | Viber bots now charge, so skip them; SMS costs money, so skip it |
| LLM | Ollama on the VM (small instruct model) | Slow is fine; batch only |
| Monitoring | `health.json` in the manifest + a workflow that opens a GitHub Issue on failure | |

Storage budget: raw AIS is the biggest consumer. Keep 90 days of raw data hot
on R2 and archive older data to HF. Keep `events` and `indicators` forever,
since they are small.

---

## 8. Contracts

All contracts live in `contracts/` as JSON Schema. Python types are generated
from them (Pydantic) and so are TypeScript types, so both sides always agree.
Contract tests run in CI.

### 8.1 Raw envelope

```json
{
  "source": "aisstream",
  "source_version": "1",
  "license": ["ATTRIBUTION"],
  "fetched_at": "2026-10-16T03:00:12Z",
  "event_time": "2026-10-16T02:59:58Z",
  "request": { "endpoint": "...", "params": {} },
  "payload_sha256": "…",
  "payload": { }
}
```

### 8.2 Answer

```json
{
  "question_id": "ferry.suspension",
  "question_version": 3,
  "scope": { "ferry_route": "matnog-allen" },
  "as_of": "2026-10-16T06:00:00Z",
  "valid_until": "2026-10-16T09:00:00Z",
  "verdict": "likely",
  "value": { "p_24h": 0.18, "p_48h": 0.71, "p_72h": 0.86, "expected_duration_h": [24, 60] },
  "confidence": "medium",
  "coverage": 0.82,
  "drivers": [
    { "feature": "forecast_wave_height_m", "value": 4.1, "effect": "+" },
    { "feature": "pagasa_signal_forecast", "value": 2, "effect": "+" }
  ],
  "evidence": [ { "kind": "advisory", "ref": "events/advisory/…", "url": "…" } ],
  "text": { "en": "…", "fil": "…" },
  "model": { "name": "ferry_logit", "version": "2026-10-01", "backtest_ref": "eval/reports/ferry.suspension/…" },
  "license": ["ATTRIBUTION"],
  "attributions": ["ECMWF", "PAGASA", "AISStream"]
}
```

### 8.3 Question spec

```yaml
# questions/tier1/ferry.suspension.yaml
id: ferry.suspension
version: 3
tier: 1
buyers: [logistics, distributors, retail]
decision: "Dispatch, hold, or reroute trucks; restock islands before a cutoff."
ask:
  en: "Will sailings on {route} be suspended, and for how long?"
  fil: "Masususpinde ba ang biyahe sa {route}, at gaano katagal?"
scope: { entity: ferry_route, values: reference/ferry_routes.csv }
cadence: { default: 6h, active_storm: 1h }
horizons_h: [24, 48, 72, 120]
inputs:
  indicators: [route_wind_wave_forecast, storm_signal_forecast, ferry_activity]
  events: [advisory]
model: nightfall.answers.questions.ferry_suspension:Model
baseline: nightfall.eval.baselines:signal_rule
metric: { primary: brier, secondary: [recall_48h] }
ship_when: "brier < baseline.brier and recall_48h >= 0.8 over >= 15 storms"
min_coverage: 0.6
outputs: [web, bot, feed]
```

---

## 9. Core data model (abbreviated)

| Table | Key | Main columns |
|---|---|---|
| `entities.vessel` | `vessel_id` (IMO, else MMSI) | mmsi, imo, name, type, dwt, flag, first/last_seen |
| `entities.port` | `port_id` (UN/LOCODE) | name, country, geom, anchorage_ids[], berth_zone_ids[] |
| `entities.ferry_route` | `route_id` | ports[2], waypoints (line), operators[], typical_daily_sailings |
| `entities.region` | `psgc_code` | level, name, geom, h3_cells[] |
| `entities.commodity` | `commodity_id` | hs_codes[], display names (en/fil), retail item mapping |
| `events.port_call` | `call_id` | vessel_id, port_id, arrive_anchorage, berth_start, berth_end, depart, draught_in/out, `known_at` |
| `events.voyage` | `voyage_id` | vessel_id, origin_port, dest_port, depart, eta, arrive, commodity_probs{} |
| `events.ferry_sailing` | `sailing_id` | route_id, vessel_id, depart, arrive |
| `events.storm_forecast` | `(storm_id, issued_at, lead_h)` | position, max_wind, radii, source |
| `events.advisory` | `advisory_id` | issuer, type (suspension/lifted/…), entities[], text_hash, url, `known_at` |
| `events.price_obs` | `(item, region, date, source)` | price, unit, kind (retail/wholesale/SRP) |
| `events.fuel_adjustment` | `(product, effective_date)` | delta_php_per_l, source |
| `indicators.*` | `(entity, ts)` | value, baseline, zscore, coverage |
| `answers.*` | `(question_id, scope, as_of)` | §8.2 |

Rule for every table: `event_time` (when it happened) and `known_at` (when
we could have known it). Features are always built with `known_at <= as_of`.

---

## 10. Directory layout

```
nightfall/
├── ARCHITECTURE.md
├── questions/                         # the product. One YAML per question.
│   ├── tier1/
│   │   ├── fuel.next_week.yaml
│   │   ├── ports.wait.yaml
│   │   ├── ferry.suspension.yaml
│   │   ├── staples.import_pipeline.yaml
│   │   ├── staples.price_direction.yaml
│   │   └── retail.stock_up.yaml
│   ├── tier2/  lanes.upstream_disruption.yaml  typhoon.asset_exposure.yaml  lastmile.flood_access.yaml
│   └── tier3/  suppliers.activity.yaml  aircargo.capacity.yaml
│
├── contracts/                         # JSON Schema: one source of truth for Python and TS
│   ├── envelope.schema.json
│   ├── answer.schema.json
│   ├── question.schema.json
│   ├── manifest.schema.json
│   └── tables/                        # published table schemas
│
├── reference/                         # small, versioned, hand-curated
│   ├── ports.csv  anchorages.geojson  berth_zones.geojson
│   ├── ferry_routes.csv  ferry_routes.geojson
│   ├── origin_ports.csv               # commodity → typical loading ports
│   ├── chokepoints.geojson
│   ├── commodities.csv                # HS codes ↔ retail items ↔ fil names
│   ├── psgc_regions.csv
│   └── cargo_operators.csv            # airline ICAO codes
│
├── pipeline/
│   ├── pyproject.toml                 # uv; single package, enforced layers
│   ├── importlinter.ini               # core ← sources ← detect/nlp ← indicators ← answers ← publish
│   ├── src/nightfall/
│   │   ├── core/
│   │   │   ├── time.py                # UTC, Manila display, as-of helpers
│   │   │   ├── geo.py                 # H3, geofences, route sampling
│   │   │   ├── ids.py
│   │   │   ├── license.py             # License flags + propagation
│   │   │   ├── envelope.py
│   │   │   ├── lake.py                # read/write partitions: local | R2 | HF
│   │   │   ├── http.py                # retry, rate limit, caching, UA
│   │   │   └── settings.py
│   │   ├── sources/                   # one module per source; Source protocol
│   │   │   ├── base.py  registry.py
│   │   │   ├── ships/      aisstream.py  portwatch.py
│   │   │   ├── flights/    adsb_lol.py
│   │   │   ├── weather/    ecmwf_open.py  gfs.py  wavewatch.py  gdacs.py  jtwc.py  pagasa.py  ibtracs.py
│   │   │   ├── satellite/  copernicus.py  firms.py  blackmarble.py
│   │   │   ├── markets/    eia.py  bsp_fx.py  da_prices.py  psa.py  doe_fuel.py  wb_pinksheet.py
│   │   │   └── text/       gdelt.py  rss.py  pcg.py  ppa.py  marina.py
│   │   ├── collectors/
│   │   │   └── ais.py                 # websocket → buffered hourly Parquet → R2
│   │   ├── detect/                    # entities/staging → events
│   │   │   ├── port_calls.py  voyages.py  ferry_sailings.py
│   │   │   ├── commodity_attribution.py
│   │   │   ├── storms.py              # track × route/port/region intersection
│   │   │   └── floods.py              # Sentinel-1 change detection
│   │   ├── nlp/
│   │   │   ├── llm.py                 # provider interface (Ollama default)
│   │   │   ├── extract.py             # advisory / price / policy event extraction
│   │   │   ├── geotag.py  dedupe.py
│   │   │   └── lang.py                # fil/ceb/en handling
│   │   ├── features/                  # as-of-safe feature builders
│   │   ├── indicators/
│   │   │   ├── congestion.py  ferry_activity.py  import_pipeline.py
│   │   │   ├── route_weather.py  disruption.py  activity.py
│   │   ├── answers/
│   │   │   ├── spec.py                # load/validate questions/*.yaml
│   │   │   ├── engine.py              # run question × scope × as_of
│   │   │   ├── render.py              # plain-language en/fil text
│   │   │   └── questions/             # one module per question (Model class)
│   │   │       ├── fuel_next_week.py
│   │   │       ├── ports_wait.py
│   │   │       ├── ferry_suspension.py
│   │   │       ├── staples_import_pipeline.py
│   │   │       ├── staples_price_direction.py
│   │   │       └── retail_stock_up.py
│   │   ├── eval/
│   │   │   ├── backtest.py            # walk-forward harness, as-of replay
│   │   │   ├── baselines.py
│   │   │   └── metrics.py
│   │   ├── publish/
│   │   │   ├── bake.py  tiles.py  feeds.py  manifest.py  license_gate.py
│   │   ├── notify/
│   │   │   ├── telegram.py  messenger.py  digest.py
│   │   ├── lineage.py
│   │   └── cli.py                     # nightfall ingest|collect|build|answer|backtest|publish|lineage
│   ├── transform/                     # dbt-duckdb
│   │   ├── dbt_project.yml  profiles.yml
│   │   ├── models/{staging,entities,features}/
│   │   ├── macros/
│   │   └── tests/
│   └── tests/
│       ├── fixtures/                  # recorded real payloads per source
│       ├── unit/
│       ├── contract/                  # schemas, adapters vs. fixtures
│       ├── asof/                      # leakage tests
│       └── e2e/                       # fixtures → answers, offline
│
├── eval/
│   ├── ground_truth/                  # curated labels (past suspensions, adjustments)
│   ├── storms/                        # replay sets for typhoon questions
│   └── reports/                       # generated; published with the site
│
├── apps/
│   ├── web/                           # Vite + React + MapLibre + DuckDB-WASM
│   │   └── src/
│   │       ├── data/                  # manifest, DuckDB-WASM queries, generated types
│   │       ├── questions/             # one page per question: simple + analyst views
│   │       ├── map/                   # layers: vessels, ports, routes, storms, floods
│   │       ├── track-record/          # public backtest results (builds trust)
│   │       └── components/
│   └── bot/                           # Cloudflare Worker
│       ├── src/  (webhook, subscribe by region, daily push)
│       ├── schema.sql                 # D1: subscribers, region, language, feedback
│       └── wrangler.toml
│
├── infra/
│   ├── vm/                            # cloud-init, systemd units, healthcheck
│   ├── cloudflare/                    # R2, Pages, Worker config notes
│   └── scripts/                       # bootstrap, backfill, archive-to-hf
│
├── notebooks/                         # exploration only; never imported
├── docs/adr/                          # one file per decision
└── .github/workflows/
    ├── ci.yml                         # lint, types, unit, contract, as-of, import-linter
    ├── ingest-hourly.yml
    ├── ingest-daily.yml
    ├── storm-watch.yml                # bumps cadence when a storm is in the PH area
    ├── build-publish.yml
    ├── backtest-weekly.yml
    ├── archive.yml
    └── health.yml
```

---

## 11. Engineering conventions

- **Python:** 3.12, uv, ruff, pyright (strict on `core/` and `answers/`),
  pytest. DuckDB is the only query engine. Polars only where DuckDB is awkward.
- **TS:** strict, Biome, Vitest. Types generated from `contracts/`.
- **Source adapter contract:** `fetch(window) -> Iterable[Envelope]`. Pure apart
  from HTTP. Each has a recorded fixture and a contract test. No adapter
  imports another adapter.
- **Network-free tests:** CI never calls live APIs. Live checks run in
  `health.yml` only.
- **No-leakage test:** for each question, the backtest harness replays data at
  `as_of` and asserts that no input has `known_at > as_of`.
- **Every question ships with:** spec YAML, model module, baseline, backtest
  report, en/fil copy, and an ADR if it adds a new source.
- **Secrets:** GitHub Actions secrets and Worker secrets only. Never in the
  lake or the manifest.
- **Scraping:** check robots.txt, identify with a User-Agent, cache aggressively,
  store facts and links rather than copies of content.

---

## 12. Roadmap

Each phase ends with a **published, backtested answer**.

| Phase | Build | Exit criterion |
|---|---|---|
| **0. Foundation** | `core/`, envelope, lake on R2, contracts + codegen, CI, manifest, license gate, one adapter (EIA) end to end | `nightfall build` runs in Actions from fixtures and publishes a manifest |
| **1. Fuel** | EIA, BSP, DOE ground truth scraper, `fuel.next_week`, web page, track record page | 52-week backtest beats baselines; published every Friday |
| **2. Storms + ferries** | GDACS/JTWC/PAGASA, ECMWF/GFS/WW3, ferry routes reference, AIS collector on the VM, `ferry.suspension` | Backtest over past storms beats the signal rule |
| **3. Ports** | Port geofences, port-call detection, PortWatch, `ports.wait` | MAE beats trailing median for ports with good coverage |
| **4. Imports** | Voyages, commodity attribution, `staples.import_pipeline` | Monthly MAPE vs. PSA beats last-year baseline for rice + fuel |
| **5. Prices + store bot** | DA/PSA scrapers, `staples.price_direction`, `retail.stock_up`, Cloudflare Worker bot (Messenger/Telegram, en/fil) | Price model beats persistence for ≥ 3 items; bot live with feedback loop |
| **6. Text** | GDELT, RSS, PCG/PPA, LLM extraction, evidence links on every answer | Advisory extraction precision ≥ 0.9 on labelled set |
| **7. Tier 2** | `lanes.upstream_disruption`, `typhoon.asset_exposure` (customer sites in D1), `lastmile.flood_access` | First B2B pilot customer |
| **8. Tier 3** | Sentinel-5P/night lights, adsb.lol cargo | Add detail to Tier 1/2 answers |

Order rationale: fuel first because it is the cheapest data, has the clearest
ground truth, comes out weekly, and gets traction quickly. Storms and ferries
next because they are specific to the Philippines, hard to get elsewhere, and
the value is very visible. Flights and satellite last because they need the
most effort for the least effect on the money questions.

---

## 13. Risks

| Risk | Mitigation |
|---|---|
| Free AIS coverage is patchy in PH waters | Coverage score per port/route; suppress low-coverage answers; PortWatch as backbone |
| Licence terms change or disallow commercial use | Licence flags in code + gate; every ⚠️ source re-checked before launch; swappable adapters |
| Gov sites change format (scrapers break) | Fixture-based contract tests; `health.yml` raises an issue; keep last good data |
| Oracle VM reclaimed or down | Collector writes to R2 hourly; gaps flagged in coverage; reprovision script in `infra/vm` |
| Free-tier limits (R2 10 GB, Actions) | 90-day hot retention, HF archive, aggregates-only long term |
| Models that look good but fail live | Walk-forward backtests, baselines, public track record, ship rules in specs |
| Store-level advice causes harm (bad stock-up call) | Rules-only over validated answers; confidence shown; conservative defaults; feedback loop |
