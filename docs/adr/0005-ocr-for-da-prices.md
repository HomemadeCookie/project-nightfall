# 0005. OCR for scanned DA price files

**Status:** accepted

## Context
The DA publishes weekly NCR retail prices as PDFs. 98 of 161 files (2023-2026) have no text layer. Without
them there are about 60 weeks of history: too little to train or fairly backtest anything.

## Decision
Fall back to RapidOCR (free, offline, an optional `ocr` extra) at 200 dpi. Measured against the one file that
has both a text layer and an image: **all 16 tracked staples matched exactly**. The parser tolerates OCR's
quirks (dropped spaces, `[` for `(`, `ka` for `kg`, a lost unit), and staging drops values more than 2.5x away
from the item's median, which catches a lost decimal point.

## Consequences
- About 50 s of CPU per scanned file. Only new weekly files need it after the backfill.
- OCR can miss an item; it has not produced a wrong price in testing. Missing is the safe failure.
- Revised editions win over originals; the file's `method` (`text`/`ocr`) is kept for auditing.
