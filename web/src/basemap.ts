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

/**
 * The palette.
 *
 * Dark, because the overlay is the product and a bright basemap would compete with it for
 * attention. But land and water have to be told apart at a glance: the first version differed
 * by seven levels of luminance, which made the coastline of an archipelago something you had
 * to hunt for, and geographic context nobody can see is not context. Water is pushed darker
 * and land lighter, and roads are dimmer than the coastline they sit inside, so the order of
 * what the eye finds is tracks, then coast, then everything else.
 */
const LAND = '#1a212e';
const WATER = '#060910';
const BOUNDARY = '#303a4c';
const ROAD = '#222b3a';

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

/** `PMTiles` followed by the spec version, the first bytes of a v3 archive header. */
const PMTILES_MAGIC = 'PMTiles';
const PMTILES_VERSION = 3;

/**
 * Whether the tile archive is actually there, and is actually an archive.
 *
 * A range request rather than a HEAD, because that is what PMTiles itself needs from the host:
 * a server that answers 200 to HEAD but ignores `Range` would fail later, in the middle of
 * rendering, instead of here.
 *
 * The bytes are then inspected rather than assumed. A static host answers a missing file with
 * a page, so a successful response proves reachability and nothing about content — and handing
 * that page to the tile reader produces a complaint about magic numbers from inside a library,
 * long after the point where the app could have said the basemap simply is not published yet.
 */
export async function basemapAvailable(url: string): Promise<boolean> {
  try {
    const response = await fetch(url, { headers: { Range: 'bytes=0-15' } });
    if (response.status !== 206) return false;
    const head = new Uint8Array(await response.arrayBuffer());
    if (head.length < PMTILES_MAGIC.length + 1) return false;
    const magic = String.fromCharCode(...head.subarray(0, PMTILES_MAGIC.length));
    return magic === PMTILES_MAGIC && head[PMTILES_MAGIC.length] === PMTILES_VERSION;
  } catch {
    return false;
  }
}
