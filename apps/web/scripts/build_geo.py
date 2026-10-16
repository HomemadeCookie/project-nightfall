"""Build public/ph-regions.json from geoBoundaries PHL ADM1 (CC BY 3.0 IGO).

    python scripts/build_geo.py path/to/geoBoundaries-PHL-ADM1_simplified.geojson

Simplifies with Douglas-Peucker (~1 km), rounds to 3 decimals, drops tiny islets, and tags each region
with the code used in reference/regions.csv. The output is committed so builds need no network.
"""

import json
import math
import sys

CODES = {
    "ARMM": "BARMM", "CAR": "CAR", "NCR": "NCR", "Ilocos Region": "I", "Cagayan Valley": "II",
    "Central Luzon": "III", "Calabarzon": "IVA", "Mimaropa": "MIMAROPA", "Zamboanga Peninsula": "IX",
    "Bicol Region": "V", "Western Visayas": "VI", "Central Visayas": "VII", "Eastern Visayas": "VIII",
    "Northern Mindanao": "X", "Davao Region": "XI", "Soccsksargen": "XII", "Caraga": "XIII",
}
TOLERANCE = 0.012  # degrees
MIN_RING_AREA = 0.0006  # deg^2; drops islets too small to see at country scale


def dp(points, tol):
    if len(points) < 3:
        return points
    (x1, y1), (x2, y2) = points[0], points[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = math.hypot(dx, dy) or 1e-12
    idx, dmax = 0, 0.0
    for i in range(1, len(points) - 1):
        d = abs(dy * points[i][0] - dx * points[i][1] + x2 * y1 - y2 * x1) / norm
        if d > dmax:
            idx, dmax = i, d
    if dmax <= tol:
        return [points[0], points[-1]]
    return dp(points[: idx + 1], tol)[:-1] + dp(points[idx:], tol)


def dp_ring(ring, tol):
    """Simplify a closed ring: split at the point farthest from the start so the chord is not degenerate."""
    pts = list(ring[:-1]) if ring[0] == ring[-1] else list(ring)
    far = max(range(len(pts)), key=lambda i: (pts[i][0] - pts[0][0]) ** 2 + (pts[i][1] - pts[0][1]) ** 2)
    left, right = dp(pts[: far + 1], tol), dp(pts[far:] + [pts[0]], tol)
    return left[:-1] + right


def area(ring):
    return abs(sum(ring[i][0] * ring[(i + 1) % len(ring)][1] - ring[(i + 1) % len(ring)][0] * ring[i][1]
                   for i in range(len(ring)))) / 2


def simplify_polygon(poly):
    rings = []
    for k, ring in enumerate(poly):
        if k == 0 and area(ring) < MIN_RING_AREA:
            return None
        s = dp_ring([tuple(p) for p in ring], TOLERANCE)
        if len(s) >= 4:
            rings.append([[round(x, 3), round(y, 3)] for x, y in s])
    return rings or None


def main(src, dst="public/ph-regions.json"):
    data = json.load(open(src))
    feats = []
    for f in data["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        out = [p for p in (simplify_polygon(p) for p in polys) if p]
        name = f["properties"]["shapeName"]
        feats.append({"type": "Feature", "properties": {"code": CODES[name], "name": name},
                      "geometry": {"type": "MultiPolygon", "coordinates": out}})
    json.dump({"type": "FeatureCollection", "features": feats}, open(dst, "w"), separators=(",", ":"))
    print(dst, sum(len(r) for f in feats for p in f["geometry"]["coordinates"] for r in p), "points")


if __name__ == "__main__":
    main(*sys.argv[1:])
