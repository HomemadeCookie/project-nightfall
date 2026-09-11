/**
 * The basemap style.
 *
 * Tiles are self-hosted PMTiles served from the same origin as the app. A hosted tile service
 * would be a metered billing relationship, which invariant 0 forbids, and MapLibre's demo
 * styles are a demonstration rather than a licence to depend on.
 *
 * The basemap is deliberately optional. A missing or not-yet-built tile archive degrades to a
 * plain background with the overlay still drawn on it, because the mobility data is the
 * product and the basemap is context. Failing hard here would let a scheduled basemap job
 * take down a page whose data is perfectly fine.
 */
import type { StyleSpecification } from 'maplibre-gl';

const LAND = '#12161f';
const WATER = '#0b0e14';
const BOUNDARY = '#2a3240';
const ROAD = '#232b38';

export function blankStyle(): StyleSpecification {
  return {
    version: 8,
    // Fonts and sprites are omitted rather than pointed at a CDN: an external asset request
    // would be the browser talking to a third party (invariant 1).
    sources: {},
    layers: [{ id: 'background', type: 'background', paint: { 'background-color': WATER } }],
  };
}

/**
 * Style over a Protomaps basemap archive.
 *
 * A deliberately small subset of the schema: land, water, boundaries, and major roads. The
 * overlay is what the eye should go to, and every additional basemap layer is fill rate spent
 * against the frame budget.
 */
export function basemapStyle(pmtilesUrl: string): StyleSpecification {
  return {
    version: 8,
    sources: {
      protomaps: {
        type: 'vector',
        url: `pmtiles://${pmtilesUrl}`,
        attribution: '© OpenStreetMap contributors, ODbL · Protomaps',
      },
    },
    layers: [
      { id: 'background', type: 'background', paint: { 'background-color': WATER } },
      {
        id: 'earth',
        type: 'fill',
        source: 'protomaps',
        'source-layer': 'earth',
        paint: { 'fill-color': LAND },
      },
      {
        id: 'water',
        type: 'fill',
        source: 'protomaps',
        'source-layer': 'water',
        paint: { 'fill-color': WATER },
      },
      {
        id: 'boundaries',
        type: 'line',
        source: 'protomaps',
        'source-layer': 'boundaries',
        paint: { 'line-color': BOUNDARY, 'line-width': 0.6 },
      },
      {
        id: 'roads',
        type: 'line',
        source: 'protomaps',
        'source-layer': 'roads',
        minzoom: 8,
        filter: ['in', 'kind', 'highway', 'major_road'],
        paint: { 'line-color': ROAD, 'line-width': 0.7 },
      },
    ],
  };
}

/**
 * Whether the tile archive is actually there.
 *
 * A range request rather than a HEAD, because that is what PMTiles itself needs from the host:
 * a server that answers 200 to HEAD but ignores `Range` would fail later, in the middle of
 * rendering, instead of here.
 */
export async function basemapAvailable(url: string): Promise<boolean> {
  try {
    const response = await fetch(url, { headers: { Range: 'bytes=0-15' } });
    return response.status === 206;
  } catch {
    return false;
  }
}
