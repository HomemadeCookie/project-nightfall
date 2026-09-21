/**
 * The cross-language contract, against a real serving set.
 *
 * `src/workers/decode.test.ts` builds its fixtures in JavaScript, so it proves the reader
 * matches the *declared* layout. This suite proves the writer does too: it decodes the
 * artifacts the Python bake stage actually produced and checks them against the manifest the
 * same run published. Drift between the two would otherwise surface only as a map drawing
 * plausible nonsense.
 *
 * It requires a serving set and fails without one rather than skipping, because a contract
 * test that quietly passes with nothing to check is worse than no test at all. Run it after
 * the pipeline:
 *
 *     uv run --project pipeline nightfall bake && npm run test:contract
 */
import { readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import { artifactSpan, type Manifest, parseManifest } from '../src/manifest';
import { readString } from '../src/workers/bundles';
import { decodePoints, decodeTracks } from '../src/workers/decode';

const SERVING = resolve(process.env.NIGHTFALL_SERVING ?? '../build/serving');

function read(name: string): ArrayBuffer {
  const bytes = readFileSync(join(SERVING, name));
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

const manifest: Manifest = parseManifest(
  JSON.parse(readFileSync(join(SERVING, 'manifest.json'), 'utf8')),
);

const [west, south, east, north] = manifest.bounds;
const epochMs = new Date(manifest.layers[0]?.epoch ?? manifest.generated_at).getTime();

describe('the published manifest', () => {
  it('describes at least one track tier and one point layer', () => {
    expect(manifest.layers.filter((layer) => layer.kind === 'tracks').length).toBeGreaterThan(0);
    expect(manifest.layers.filter((layer) => layer.kind === 'points')).toHaveLength(1);
  });

  it('credits every source, because attribution is a licence obligation', () => {
    expect(manifest.attributions.length).toBeGreaterThan(0);
    for (const credit of manifest.attributions) {
      expect(credit.licence).not.toBe('');
      expect(credit.url).toMatch(/^https:\/\//);
    }
  });

  it('carries the sampling notice the overlay must not be read without', () => {
    expect(manifest.sampling_notice).toMatch(/sampled|historical|fixture/i);
  });

  it('publishes entity and fix counts, and a slider domain equal to the baked min/max', () => {
    expect(['live', 'archive', 'fixture', 'mixed']).toContain(manifest.observation_kind);
    expect(manifest.census.air.position_fixes + manifest.census.sea.position_fixes).toBeGreaterThan(
      0,
    );
    const [start, end] = artifactSpan(manifest);
    expect(end).toBeGreaterThan(start);
    if (manifest.available_from !== null && manifest.available_until !== null) {
      expect(manifest.available_from).toBe(manifest.layers[0]?.observed_from);
      expect(manifest.available_until).toBe(manifest.layers[0]?.observed_at);
    }
  });

  it('covers every zoom from the first tier upward with exactly one track tier', () => {
    const tiers = manifest.layers.filter((layer) => layer.kind === 'tracks');
    const lowest = Math.min(...tiers.map((tier) => tier.min_zoom));
    for (let zoom = lowest; zoom <= 24; zoom += 1) {
      const matching = tiers.filter((tier) => zoom >= tier.min_zoom && zoom <= tier.max_zoom);
      expect(matching, `zoom ${zoom}`).toHaveLength(1);
    }
  });
});

describe.each(manifest.layers.filter((layer) => layer.kind === 'tracks'))(
  'baked track tier $id',
  (layer) => {
    const bundle = decodeTracks(read(layer.url));

    it('decodes to the feature and vertex counts the manifest declares', () => {
      expect(bundle.length).toBe(layer.feature_count);
      expect(bundle.vertexCount).toBe(layer.budget.path_vertices);
    });

    it('stays inside the declared frame budget', () => {
      expect(bundle.vertexCount).toBeLessThanOrEqual(layer.budget.path_vertex_limit);
    });

    it('has offsets that describe exactly the vertices present', () => {
      expect(bundle.startIndices).toHaveLength(bundle.length + 1);
      expect(bundle.startIndices[0]).toBe(0);
      expect(bundle.startIndices[bundle.length]).toBe(bundle.vertexCount);
      expect(bundle.positions).toHaveLength(bundle.vertexCount * 2);
      expect(bundle.timestamps).toHaveLength(bundle.vertexCount);
    });

    it('places every vertex inside the area of interest', () => {
      // Catches a lon/lat transposition, which is otherwise invisible until someone notices
      // Philippine traffic in the Indian Ocean.
      for (let index = 0; index < bundle.vertexCount; index += 1) {
        const lon = bundle.positions[index * 2] as number;
        const lat = bundle.positions[index * 2 + 1] as number;
        expect(lon).toBeGreaterThanOrEqual(west);
        expect(lon).toBeLessThanOrEqual(east);
        expect(lat).toBeGreaterThanOrEqual(south);
        expect(lat).toBeLessThanOrEqual(north);
      }
    });

    it('orders each path forward in time', () => {
      // A path drawn out of order animates backwards and, worse, implies movement that was
      // never observed in that direction.
      for (let path = 0; path < bundle.length; path += 1) {
        const start = bundle.startIndices[path] as number;
        const end = bundle.startIndices[path + 1] as number;
        expect(end - start).toBeGreaterThanOrEqual(2);
        for (let vertex = start + 1; vertex < end; vertex += 1) {
          expect(bundle.timestamps[vertex] as number).toBeGreaterThan(
            bundle.timestamps[vertex - 1] as number,
          );
        }
      }
    });

    it('resolves timestamps against the published epoch to the declared observation window', () => {
      if (bundle.length === 0 || layer.observed_at === null) return;
      const latestMs = epochMs + (bundle.timeRange[1] as number) * 1000;
      // float32 seconds relative to the epoch: exact to well under a second over a six-hour
      // window, which is the reason the artifact stores an offset rather than a Unix time.
      expect(Math.abs(latestMs - new Date(layer.observed_at).getTime())).toBeLessThan(1000);
      expect(bundle.timeRange[0]).toBeGreaterThanOrEqual(0);
    });

    it('identifies every feature, so no sentinel row reached the browser', () => {
      for (let index = 0; index < bundle.length; index += 1) {
        expect(readString(bundle.entityIds, index)).not.toBe('');
      }
    });
  },
);

describe('the baked point layer', () => {
  const layer = manifest.layers.find((candidate) => candidate.kind === 'points');
  if (layer === undefined) throw new Error('the manifest declares no point layer');
  const bundle = decodePoints(read(layer.url));

  it('decodes to the count the manifest declares', () => {
    expect(bundle.length).toBe(layer.feature_count);
    expect(bundle.length).toBe(layer.budget.points);
    expect(bundle.length).toBeLessThanOrEqual(layer.budget.point_limit);
  });

  it('places every point inside the area of interest', () => {
    for (let index = 0; index < bundle.length; index += 1) {
      const lon = bundle.positions[index * 2] as number;
      const lat = bundle.positions[index * 2 + 1] as number;
      expect(lon).toBeGreaterThanOrEqual(west);
      expect(lon).toBeLessThanOrEqual(east);
      expect(lat).toBeGreaterThanOrEqual(south);
      expect(lat).toBeLessThanOrEqual(north);
    }
  });

  it('identifies every point', () => {
    for (let index = 0; index < bundle.length; index += 1) {
      expect(readString(bundle.entityIds, index)).not.toBe('');
    }
  });
});
