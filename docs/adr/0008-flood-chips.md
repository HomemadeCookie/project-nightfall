# 0008. Flood access is a chip, a catalog record, and a late satellite call

**Status:** accepted

## Context
`lastmile.flood_access` needs a flood map. A province of Sentinel imagery does not fit a
GitHub-hosted runner, and TerraMind-base-Flood was trained on 256×256 windows of Sentinel-2,
Sentinel-1 RTC, and a DEM. The useful number is the share of a place under flood water, not
the picture itself.

## Decision
- Watch a handful of 2.56 km squares in Pampanga, anchored on town centres. They are not
  official barangay boundaries.
- The raw lake stores STAC scene records from Microsoft Planetary Computer (Copernicus
  licence, attribution). Pixels are not envelopes.
- Four dates are chosen around the storm: clear optical and radar before, radar and optical
  after. A missing date stays missing.
- A storm whose wind field covers a square writes `lake/triggers/flood_*.json` and may say
  "likely". That sentence is the storm track, not a flood photo.
- TerraMind runs only through `nightfall flood-infer`, when a chip stack and the weights are
  present. Its class mask is a file the answer reads. The fraction is shown, and it becomes
  a flood call only after three reference events each score IoU ≥ 0.6.

## Consequences
- The daily catalog search is a few requests for the squares, not a province download.
- CI never calls the catalog or loads the weights. Tests replay a fixture and a numpy mask.
- Beating a rainfall baseline is still open, so a passing IoU bar marks the model
  `experimental`, not `validated`.
