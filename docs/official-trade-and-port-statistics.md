# Official trade and port statistics

Phase 1 of the app is a mobility overlay. These sources are landed so Phase 3
insights have **volume, commodity, and seasonality** without pretending AIS/ADS-B
are cargo.

They are **not** drawn on the map in this change. A month slider for PPA/PSA must
not be the same control as the track playhead.

## What was collected

| Source | Adapter | Live path | Analysis table |
| --- | --- | --- | --- |
| Philippine Ports Authority | `ppa` | Annual summary xlsx (2023, 2024) | `ppa_port_stats.parquet` — region × quarter |
| PSA OpenSTAT IMTS | `psa_imts` | PX-Web monthly totals 1991–present | `psa_trade_monthly.parquet` |
| UN Comtrade preview | `un_comtrade` | HS-2 × World (2019–2024); TOTAL × partners (2023–2024) | `comtrade_hs.parquet` |
| BOC Trade Data Platform | `boc_tdp` | HTML probe only | none — portal has no bulk extract (and was under maintenance when probed) |

Join keys for later overlay: PPA region name → port group; PSA/Comtrade period →
`YYYY-MM`; HS `cmd_code` → commodity group. Hinterlands are not in these files.

## Commands

Live (writes `build/raw/` then tidy parquet; never committed):

```
uv run --project pipeline nightfall collect-stats
```

Recorded fixtures only (CI, no network):

```
uv run --project pipeline python pipeline/scripts/seed_trade.py --fixtures
```

## Honesty bounds

- PPA figures are **PPA-jurisdiction ports**, not every private terminal.
- PSA values on the totals table are **million USD**.
- Comtrade preview **truncates at 500 rows**; the coverage note says so.
- None of these series is a voyage or a bill of lading.
