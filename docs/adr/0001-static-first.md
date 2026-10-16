# 0001. Batch jobs and static files, no server

**Status:** accepted

## Context
The constraint is ₱0 running cost. A database server, an API server and an always-on worker each need
a paid or reclaimable host, and each is something that can be down at 3 AM.

## Decision
Everything is a batch job over files. Raw data lands as Parquet in a lake; staging, indicators and answers
are rebuilt from it; `nightfall publish` bakes static JSON that a static site (and a Cloudflare Worker bot)
reads. State between scheduled runs lives in one rolling GitHub Release asset (`lake-latest`).

## Consequences
- Hosting, compute and storage are all on free tiers: GitHub Actions + Pages + Releases, Cloudflare Workers + KV.
- No query API for customers yet; B2B delivery is files (JSON/Parquet) until there is revenue to justify a server.
- Latency is the schedule (hourly), not real time. Fine for the questions asked.
- Releases cap at 2 GB per asset. `nightfall prune` and a push-time guard keep us under it.
