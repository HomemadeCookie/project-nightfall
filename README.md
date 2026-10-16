# Nightfall PH

Free, honest supply-chain signals for the Philippines, built from public data. It answers questions a
business actually acts on (*will diesel rise on Tuesday? is Manila port busier than normal? will the
Matnog ferry stop sailing? should I stock up this week?*) and says how far each answer can be trusted.

- **Costs ₱0 to run.** Batch jobs on GitHub Actions, a static site on GitHub Pages, an optional Telegram bot on
  Cloudflare's free tier. No servers, no paid APIs, no keys required for the core pipeline.
- **Honest by construction.** Every answer carries its confidence, the data it used, its limits, and a model
  status (`validated`, `experimental`, `unvalidated`) taken from backtest reports, never from the code.
- **Licence-aware.** A gate separates what may be shown for research from what may be sold. Today most
  answers are research-only; `docs/adr/0006-licence-gate.md` and `reference/license_reviews.yaml` say exactly why.

## What it answers

| Question | Buyer | Status today |
|---|---|---|
| `fuel.next_week`: pump-price direction next Tuesday | fleets, retail, distributors | unvalidated until 8 official adjustments are recorded |
| `ports.pressure`: is a key port busier or quieter than normal, plus a next-week forecast | importers, forwarders | experimental; forecast ships only where it beat the baseline |
| `ferry.suspension`: risk that a RoRo corridor stops sailing | logistics, island distributors | unvalidated heuristic ladder |
| `staples.arrivals`: bulk-grain and fuel cargo arriving vs normal | traders, millers | experimental nowcast |
| `staples.price_direction`: NCR staple prices over 4 weeks | distributors, retailers | forecast publishes only for items that beat trend baselines in walk-forward tests |
| `retail.stock_up`: plain-language advice per region (English and Filipino) | sari-sari stores, via distributors | rules over the above; inherits their limits |
| `lanes.upstream_disruption`, `typhoon.asset_exposure`, `aircargo.activity` | procurement, insurers | experimental |
| `lastmile.flood_access`, `suppliers.activity` | | planned (need free satellite accounts) |

Specs live in [`questions/`](questions/): the decision each one changes, the baseline it must beat, and the
rule for when it may publish.

## Try it

```bash
cd pipeline
uv sync
export NIGHTFALL_LAKE=$PWD/../lake
uv run nightfall ingest                 # fetches every source with a public, keyless API
uv run nightfall build                  # stage, answer, publish to ../dist
uv run nightfall answer --show fuel.next_week ports.pressure
cd ../apps/web && npm ci && npm run dev
```

Other commands: `backtest`, `events`, `lineage <question>`, `exposure --sites my_sites.csv`, `prune`,
`contracts`. See [`docs/runbook.md`](docs/runbook.md) for deployment, backfill and limits.

## How it fits together

```
sources/ (HTTP adapters)  ->  raw lake (Parquet, immutable, with licence + provenance)
   stage/   typed tables, publication lags  ->  core/context.py (every read is "as of" a time)
   indicators/  fuel cost, port pressure, storm exposure, price features
   answers/questions/  one module per question, spec in questions/*.yaml
   eval/  walk-forward backtests -> eval/reports/*.json   (decides each answer's status)
   publish/  licence gate, manifest, static JSON  ->  apps/web (React) and apps/bot (Telegram)
```

The layering is enforced in CI (`import-linter`). The reasoning behind the larger decisions is in
[`docs/adr/`](docs/adr/); the original product spec is [`ARCHITECTURE.md`](ARCHITECTURE.md).

```
questions/    the product: one YAML spec per question
reference/    curated ports, ferry corridors, regions, commodities, price items, licence reviews
pipeline/     Python package `nightfall` (uv), ~150 tests
apps/web/     React + d3-geo site, English/Filipino, light/dark, types generated from the answer schema
apps/bot/     Telegram bot as a Cloudflare Worker (free tier), fully unit-tested without network
eval/         ground truth and generated backtest reports
contracts/    JSON Schemas generated from the Pydantic models
infra/        lake persistence + health-check scripts used by the workflows
.github/      ci, hourly pipeline, weekly backtest, keepalive
```

## Data sources (all free)

| Source | Used for | Key needed | Commercial use |
|---|---|---|---|
| IMF PortWatch | port calls, import tonnage, strait transits | no | unclear |
| EIA, Frankfurter (ECB) | fuel cost proxy, USD/PHP | no (EIA `DEMO_KEY`) | yes |
| DA Bantay Presyo | NCR weekly retail prices (text PDFs + OCR for scanned ones) | no | needs DA approval |
| GDACS / JTWC, IBTrACS | storm tracks, history | no | unclear / yes |
| NOAA GFS + GFS-Wave | wind and waves along ferry corridors (preferred) | no | yes (public domain) |
| Open-Meteo | same, fallback only | no | **no** |
| World Bank Pink Sheet | world commodity prices | no | yes |
| adsb.lol | freighter traffic near airports | no | yes (ODbL) |
| AISStream (optional) | berth wait times | free key | unclear |
| Philippine news RSS, GDELT | event extraction, ground truth | no | headlines and links only |

## Limits worth knowing

- Local prices exist for **Metro Manila only**; the DA publishes no machine-readable regional series.
- Port data measures vessel-call **volume**, not berth wait, until AIS is switched on.
- Fuel is modelled from NY Harbor spot prices as a stand-in for Singapore benchmarks, with no fitted coefficients.
- Ferry risk is a transparent heuristic. It is not a probability and has not been validated against real notices.
- Free-tier hosting is fine for this scale; see the runbook for the specific limits.
