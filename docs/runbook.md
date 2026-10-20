# Runbook

## Local setup
```bash
cd pipeline && uv sync                 # add --extra ocr for scanned DA PDFs
export NIGHTFALL_LAKE=$PWD/../lake     # where data lives (gitignored)
uv run nightfall ingest                # all sources, last few weeks
uv run nightfall stage
uv run nightfall build                 # stage + answers + dist/
cd ../apps/web && npm ci && npm run dev
```

Flood squares are answered on every build (storm track, or a mask if you have placed one under
`$NIGHTFALL_LAKE/flood_masks/<chip_id>/<item_id>.npy`). TerraMind itself is a separate step and is
not installed with the default environment:

```bash
# stack.npz must contain s2 (4,12,H,W), s1 (4,2,H,W), dem (H,W)
uv run nightfall flood-infer --stack stack.npz --config terramind_flood.yaml --checkpoint model.pt --out mask.npy
uv run nightfall backtest --only lastmile.flood_access
```

Reference masks for that backtest are `eval/flood_reference/<event>.npz` with arrays `pred` and `ref`.
None are shipped yet, so the satellite call stays withheld.

## First-time history (needed for honest backtests)
```bash
uv run nightfall ingest eia frankfurter portwatch --lookback-days 1100
uv run --extra ocr nightfall ingest da_prices    # 160 PDFs; ~100 are scanned, about 50 s each
uv run nightfall ingest worldbank ibtracs
uv run nightfall stage && uv run nightfall backtest
```
PortWatch is fetched in 60-day windows because one large date range times out on the server.

## Deploy (all free)
1. Push the repo to GitHub (public repos get unlimited Actions minutes).
2. Settings, Pages: source "GitHub Actions". The `pipeline` workflow publishes the site hourly.
3. Nothing else is required. No secrets for the core pipeline.

### Telegram bot (optional)
```bash
cd apps/bot && npm ci
npx wrangler kv namespace create USERS          # paste the id into wrangler.toml
npx wrangler secret put TELEGRAM_TOKEN          # from @BotFather
npx wrangler secret put WEBHOOK_SECRET          # any random string
# set SITE_URL in wrangler.toml to the published Pages URL
npx wrangler deploy
TELEGRAM_TOKEN=... WEBHOOK_SECRET=... WORKER_URL=https://nightfall-bot.<you>.workers.dev npm run set-webhook
```

### AIS (optional)
Get a free key at aisstream.io, add it as the repository secret `AISSTREAM_API_KEY`, then run
`nightfall collect-ais --seconds 3300` on a schedule or a free VM. Without it, `ports.pressure` simply has no wait times.

## Free-tier limits that matter
| Limit | Where | What to do |
|---|---|---|
| 2 GB per release asset | the lake | `nightfall prune --keep-days 180` weekly (already in `backtest.yml`); push script refuses at 1.8 GB |
| Scheduled workflows pause after 60 idle days | GitHub | `keepalive.yml` re-enables them weekly |
| 1,000 KV writes/day | bot | fine for hundreds of users; move prefs to D1 beyond that |
| EIA `DEMO_KEY` rate limit | EIA | register a free key, set `EIA_API_KEY` |
| GDELT: 1 request / 5 s | GDELT | handled; a throttled topic is skipped, not fatal |

## When something looks wrong
- **Site says a source is stale:** `dist/manifest.json` -> `sources[].fresh`. The pipeline opens an issue automatically (`infra/scripts/health.py`).
- **A question shows an error:** `nightfall answer --only <id>` prints the traceback; other questions keep running.
- **A forecast disappeared:** check `eval/reports/<id>.json`. Forecasts publish only while they beat their baseline.
- **Why was an answer blocked in commercial mode:** `dist/blocked.json`, or `nightfall lineage <question>`.
- **Rebuild everything from raw:** staging is idempotent: `nightfall stage && nightfall publish`.
