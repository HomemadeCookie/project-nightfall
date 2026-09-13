import { describe, expect, it } from 'vitest';

import {
  artifactSpan,
  layersForZoom,
  ManifestVersionError,
  overallFreshness,
  parseManifest,
  SUPPORTED_SCHEMA_VERSION,
} from './manifest';

function layer(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: 'mobility-tracks-z9',
    kind: 'tracks',
    url: 'mobility_tracks_z9.abc123.arrow',
    format: 'arrow-ipc',
    schema_version: SUPPORTED_SCHEMA_VERSION,
    min_zoom: 9,
    max_zoom: 11,
    epoch: '2026-09-11T00:00:00Z',
    observed_from: '2026-09-11T00:00:00Z',
    observed_at: '2026-09-11T06:00:00Z',
    freshness: 'fresh',
    feature_count: 2,
    budget: {
      path_vertices: 10,
      path_vertex_limit: 300_000,
      points: 0,
      point_limit: 500_000,
      bytes: 2048,
    },
    ...overrides,
  };
}

function manifest(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema_version: SUPPORTED_SCHEMA_VERSION,
    run_id: 'local',
    generated_at: '2026-09-11T06:05:00Z',
    bounds: [116.0, 4.0, 127.0, 21.0],
    initial_view: { longitude: 121.0, latitude: 13.0, zoom: 6 },
    layers: [layer()],
    attributions: [
      { source: 'adsb.lol', licence: 'ODbL-1.0', url: 'https://adsb.lol', text: 'adsb.lol' },
    ],
    sources: [{ source: 'adsb.lol', state: 'ok', observed_at: null, detail: null }],
    sampling_notice: 'Positions are sampled in short scheduled windows.',
    observation_kind: 'live',
    available_from: '2026-09-11T00:00:00Z',
    available_until: '2026-09-11T06:00:00Z',
    census: {
      air: { unique_entities: 2, position_fixes: 10, track_segments: 2, isolated_points: 0 },
      sea: { unique_entities: 0, position_fixes: 0, track_segments: 0, isolated_points: 0 },
    },
    ...overrides,
  };
}

describe('parseManifest', () => {
  it('accepts a manifest the pipeline would produce', () => {
    const parsed = parseManifest(manifest());
    expect(parsed.layers[0]?.id).toBe('mobility-tracks-z9');
    expect(parsed.bounds).toHaveLength(4);
  });

  it('refuses a schema version this build cannot read', () => {
    // The whole point of the check: a newer artifact read by older code is how a column that
    // changed meaning becomes a plausible-looking wrong number on screen.
    expect(() => parseManifest(manifest({ schema_version: SUPPORTED_SCHEMA_VERSION + 1 }))).toThrow(
      ManifestVersionError,
    );
  });

  it('rejects a manifest missing a field the app depends on', () => {
    const broken = manifest();
    delete (broken as { sampling_notice?: unknown }).sampling_notice;
    expect(() => parseManifest(broken)).toThrow();
  });

  it('rejects a freshness value it does not know how to present', () => {
    expect(() =>
      parseManifest(manifest({ layers: [layer({ freshness: 'probably-fine' })] })),
    ).toThrow();
  });
});

describe('layersForZoom', () => {
  const parsed = parseManifest(
    manifest({
      layers: [
        layer({ id: 'z9', min_zoom: 9, max_zoom: 11 }),
        layer({ id: 'z12', min_zoom: 12, max_zoom: 24 }),
        layer({
          id: 'points',
          kind: 'points',
          min_zoom: 0,
          max_zoom: 24,
          budget: {
            path_vertices: 0,
            path_vertex_limit: 300_000,
            points: 3,
            point_limit: 500_000,
            bytes: 900,
          },
        }),
      ],
    }),
  );

  it('picks exactly one track tier per zoom, with no gap between tiers', () => {
    for (const zoom of [9, 10, 11, 12, 18, 24]) {
      expect(layersForZoom(parsed, zoom, 'tracks')).toHaveLength(1);
    }
    expect(layersForZoom(parsed, 11, 'tracks')[0]?.id).toBe('z9');
    expect(layersForZoom(parsed, 12, 'tracks')[0]?.id).toBe('z12');
  });

  it('does not mix kinds', () => {
    expect(layersForZoom(parsed, 6, 'tracks')).toHaveLength(0);
    expect(layersForZoom(parsed, 6, 'points')).toHaveLength(1);
  });
});

describe('artifactSpan', () => {
  it('is the baked min/max in artifact seconds, which is the slider domain', () => {
    expect(artifactSpan(parseManifest(manifest()))).toEqual([0, 6 * 3600]);
  });
});

describe('overallFreshness', () => {
  it('reports the worst layer, because the badge must not flatter the build', () => {
    const parsed = parseManifest(
      manifest({
        layers: [layer({ freshness: 'fresh' }), layer({ id: 'other', freshness: 'stale' })],
      }),
    );
    expect(overallFreshness(parsed)).toBe('stale');
  });

  it('is fresh only when every layer is', () => {
    expect(overallFreshness(parseManifest(manifest()))).toBe('fresh');
  });
});
