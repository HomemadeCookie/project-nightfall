/**
 * The basemap probe decides whether the map draws over tiles or over a flat background, and
 * it is the only thing standing between an unpublished archive and an error raised from inside
 * the tile reader. These cases are the responses a free static host actually produces.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { basemapAvailable, basemapStyle } from './basemap';

const URL_UNDER_TEST = 'https://example.invalid/serving/basemap.pmtiles';

// Explicitly backed by an `ArrayBuffer`, which is what `Response` accepts as a body: the
// default `ArrayBufferLike` also admits a `SharedArrayBuffer`, which it does not.
function pmtilesHeader(): Uint8Array<ArrayBuffer> {
  const head = new Uint8Array(new ArrayBuffer(16));
  head.set([...'PMTiles'].map((character) => character.charCodeAt(0)));
  head[7] = 3;
  return head;
}

function respond(body: BodyInit, status: number): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(body, { status })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('basemapStyle', () => {
  const style = basemapStyle('/serving/basemap.pmtiles');

  it('asks every fill for polygons, because the water layer also carries rivers as lines', () => {
    const fills = style.layers.filter((layer) => layer.type === 'fill');
    expect(fills.map((layer) => layer.id)).toEqual(['earth', 'water']);
    for (const layer of style.layers) {
      if (layer.type !== 'fill') continue;
      expect(layer.filter, layer.id).toEqual(['==', '$type', 'Polygon']);
    }
  });

  it('draws only provinces and countries, not the municipal web', () => {
    const boundaries = style.layers.find((layer) => layer.id === 'boundaries');
    if (boundaries?.type !== 'line') throw new Error('expected a line layer');
    expect(boundaries.filter).toEqual(['in', 'kind', 'country', 'region']);
  });

  it('draws the national road network rather than every sealed road', () => {
    const roads = style.layers.find((layer) => layer.id === 'roads');
    if (roads?.type !== 'line') throw new Error('expected a line layer');
    expect(roads.filter).toEqual(['in', 'kind_detail', 'motorway', 'trunk', 'primary']);
  });
});

describe('basemapAvailable', () => {
  it('accepts a partial response that begins with a version 3 archive header', async () => {
    respond(pmtilesHeader(), 206);
    await expect(basemapAvailable(URL_UNDER_TEST)).resolves.toBe(true);
  });

  it('rejects the page a static host serves in place of a missing archive', async () => {
    respond('<!doctype html><title>404</title>', 206);
    await expect(basemapAvailable(URL_UNDER_TEST)).resolves.toBe(false);
  });

  it('rejects a host that ignores the range request, since the reader depends on ranges', async () => {
    respond(pmtilesHeader(), 200);
    await expect(basemapAvailable(URL_UNDER_TEST)).resolves.toBe(false);
  });

  it('rejects an archive written to a version this build does not read', async () => {
    const head = pmtilesHeader();
    head[7] = 4;
    respond(head, 206);
    await expect(basemapAvailable(URL_UNDER_TEST)).resolves.toBe(false);
  });

  it('treats an unreachable host as no basemap rather than raising', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('network error');
      }),
    );
    await expect(basemapAvailable(URL_UNDER_TEST)).resolves.toBe(false);
  });
});
