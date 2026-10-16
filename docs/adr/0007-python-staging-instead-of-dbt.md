# 0007. Python staging instead of dbt

**Status:** accepted (supersedes the dbt line in ARCHITECTURE.md)

## Context
The first design used dbt-duckdb for staging. The hard parts of staging here are not SQL: parsing GDACS
track labels, PDF/OCR text, nested forecast JSON, per-source publication lags.

## Decision
Staging is plain Python functions (`stage/*.py`) that read raw envelopes and return typed Arrow tables.
DuckDB remains the query engine for the as-of Context and for ad-hoc analysis.

## Consequences
- One toolchain, one test runner, no dbt install in CI.
- We give up dbt's lineage graph and generic tests; `nightfall lineage <question>` and pytest cover the need.
