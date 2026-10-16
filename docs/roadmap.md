# Roadmap: what is not built yet, and what each item needs

Everything below is excluded on purpose. Nothing here is faked in the product.

| Item | Why it matters | What it needs | Cost |
|---|---|---|---|
| Commercial-safe weather (NOAA GFS + WaveWatch III) | Unblocks `ferry.suspension` for paying users (ADR 0003) | GRIB adapter (`eccodes`), sample at `ferry_waypoints()` | ₱0 |
| Live AIS in production | Berth wait times, forward 30-day import pipeline | Free AISStream key as a repo secret; verify AISStream terms for commercial use | ₱0 |
| Suspension ground truth | Turns the ferry ladder into a calibrated probability | Collect PCG/MARINA/operator notices; `events` already extracts candidates | ₱0 |
| Fuel ground truth | Validates `fuel.next_week` | `nightfall events --append-ground-truth` runs weekly; need 8+ confirmed adjustments (review each row) | ₱0 |
| Regional prices outside NCR | Store-level advice outside Metro Manila | No free machine-readable source found. Candidates: PSA OpenSTAT (blocks scripted access), DA regional bulletins | ₱0 |
| `lastmile.flood_access` | Which delivery areas are flooded | Sentinel-1 change detection; free Copernicus Data Space account (not created by this project) | ₱0 |
| `suppliers.activity` | Supplier-region pulse | Sentinel-5P NO2 + VIIRS night lights; free NASA/Copernicus accounts | ₱0 |
| Messenger channel | Where most store owners actually are | Meta app review + business verification; Telegram works today | ₱0 |
| Licence clearances | Selling anything | Written permission per `reference/license_reviews.yaml` (DA, IMF PortWatch, GDACS, AISStream) | ₱0, but needs people |
| Paid API for B2B | Customers who want an endpoint, not files | A small server or Cloudflare Worker over the baked JSON | Free tier first |

## Order that makes sense
1. Licence clearances (they gate revenue and cost nothing).
2. Commercial-safe weather.
3. Let fuel ground truth accumulate (about 8 weeks), then read the first real verdict.
4. AIS key, so `ports.pressure` can report waits.
5. Flood access, for the logistics buyers who care most about last-mile reliability.
