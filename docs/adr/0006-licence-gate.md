# 0006. A licence gate between research and commercial output

**Status:** accepted

## Context
Several free sources forbid or leave unclear commercial use. Philippine government data (DA, PSA, PAGASA) is not
copyrighted, but RA 8293 s.176 requires the agency's prior approval to exploit a government work *for profit*.
A paid product built on unverified licences is a liability.

## Decision
Each source declares `License` flags in code. `reference/license_reviews.yaml` records written clearance.
Every answer carries the sources it used. `nightfall publish --mode research` (the free public site) labels
each answer `commercial_ok`; `--mode commercial` drops anything not cleared and writes `blocked.json` with reasons.

## Consequences
- Today only fuel and air-cargo answers pass the commercial gate. Everything else needs a licence action,
  listed per source in the review file.
- Clearing a source is a documented, reviewable change, not a code edit.
