# 0004. Ferry suspension is an ordinal risk, not a probability

**Status:** accepted

## Context
The spec asked for P(suspended) at 24/48/72/120 h. A probability implies calibration, and calibration needs
labelled suspension notices. We have none yet (Coast Guard advisories are not machine-readable).

## Decision
Publish `low | watch | likely` from a transparent ladder over forecast wind, gusts, waves and storm
distance (thresholds anchored on PAGASA wind-signal bands). The answer is marked `unvalidated`.
`detect/text_events.py` already extracts "sea trips suspended" headlines; once enough accumulate in
`eval/ground_truth/`, a calibrated model can replace the ladder and earn a probability.

## Consequences
- We do not display a number we cannot defend.
- The ladder is easy to audit and to explain to an operator.
