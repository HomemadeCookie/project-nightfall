# 0002. Every read goes through an as-of Context

**Status:** accepted

## Context
Backtests that quietly use data from after the forecast time look great and are worthless. In this
project the risk is real: PortWatch lags about a week, EIA a day, DA prices a few days.

## Decision
Staged tables carry an `available_on` date (event date + a publication lag) or an `issued_at` time.
`Context.rows()` is the only way answers and indicators read data, and it adds `<column> <= as_of`
itself. A test fails if a staged table has no as-of rule. Backfilled history has no honest fetch time,
so lags are modelled per source (`stage/common.py: PUBLICATION_LAG_DAYS`) instead of trusting `fetched_at`.

## Consequences
- Leakage is structurally impossible rather than a code-review item. `test_price_model_is_leak_free`
  proves a forecast at time T is unchanged by data that arrives later.
- The same `predict_at` function serves live answers and walk-forward backtests, so the backtest measures
  exactly what ships.
- Lags are estimates. If a source's real lag is longer than modelled, backtests are mildly optimistic.
