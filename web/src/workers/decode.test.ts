/**
 * The Arrow layout contract, from the reading side.
 *
 * A mistake here does not raise: the offsets shift and the map draws confident nonsense. The
 * fixtures below are built with the same Arrow types the bake stage declares
 * (`pipeline/src/nightfall/bake/artifacts.py`), and `pipeline/tests/test_artifacts.py` pins
 * the same layout from the writing side. `test/contract.test.ts` closes the loop against a
 * real baked artifact in CI.
 */
import {
  Field,
  FixedSizeList,
  Float32,
  Float64,
  List,
  Table,
  tableToIPC,
  Utf8,
  vectorFromArray,
} from 'apache-arrow';
import { describe, expect, it } from 'vitest';

import { MODE_AIR, MODE_SEA, readString } from './bundles';
import { decodePoints, decodeTracks } from './decode';

const POINT_TYPE = new FixedSizeList(2, new Field('item', new Float64(), false));
const PATH_TYPE = new List(new Field('item', POINT_TYPE, false));
const TIMESTAMPS_TYPE = new List(new Field('item', new Float32(), false));

interface TrackFixture {
  mode: 'air' | 'sea';
  entityId: string;
  label: string;
  path: Array<[number, number]>;
  timestamps: number[];
}

function tracksIPC(tracks: TrackFixture[]): ArrayBuffer {
  const table = new Table({
    source: vectorFromArray(
      tracks.map((track) => (track.mode === 'sea' ? 'aisstream' : 'adsb_lol')),
      new Utf8(),
    ),
    mode: vectorFromArray(
      tracks.map((track) => track.mode),
      new Utf8(),
    ),
    entity_id: vectorFromArray(
      tracks.map((track) => track.entityId),
      new Utf8(),
    ),
    label: vectorFromArray(
      tracks.map((track) => track.label),
      new Utf8(),
    ),
    path: vectorFromArray(
      tracks.map((track) => track.path),
      PATH_TYPE,
    ),
    timestamps: vectorFromArray(
      tracks.map((track) => track.timestamps),
      TIMESTAMPS_TYPE,
    ),
  });
  return bufferOf(tableToIPC(table, 'file'));
}

function pointsIPC(
  points: Array<{
    mode: 'air' | 'sea';
    entityId: string;
    label: string;
    lon: number;
    lat: number;
    t: number;
  }>,
): ArrayBuffer {
  const table = new Table({
    source: vectorFromArray(
      points.map((point) => (point.mode === 'sea' ? 'aisstream' : 'adsb_lol')),
      new Utf8(),
    ),
    mode: vectorFromArray(
      points.map((point) => point.mode),
      new Utf8(),
    ),
    entity_id: vectorFromArray(
      points.map((point) => point.entityId),
      new Utf8(),
    ),
    label: vectorFromArray(
      points.map((point) => point.label),
      new Utf8(),
    ),
    position: vectorFromArray(
      points.map((point): [number, number] => [point.lon, point.lat]),
      POINT_TYPE,
    ),
    timestamp: vectorFromArray(
      points.map((point) => point.t),
      new Float32(),
    ),
  });
  return bufferOf(tableToIPC(table, 'file'));
}

function bufferOf(bytes: Uint8Array): ArrayBuffer {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

const FIXTURES: TrackFixture[] = [
  {
    mode: 'air',
    entityId: 'aa1234',
    label: 'PR123',
    path: [
      [121.0, 14.5],
      [121.1, 14.6],
      [121.2, 14.7],
    ],
    timestamps: [0, 30, 60],
  },
  {
    mode: 'sea',
    entityId: '548123456',
    label: 'MV EXAMPLE',
    path: [
      [120.9, 14.4],
      [120.95, 14.45],
    ],
    timestamps: [10, 70],
  },
];

describe('decodeTracks', () => {
  const bundle = decodeTracks(tracksIPC(FIXTURES));

  it('counts paths, not vertices, as the feature length', () => {
    expect(bundle.length).toBe(2);
    expect(bundle.vertexCount).toBe(5);
  });

  it('reads offsets that count vertices, which is what deck.gl startIndices means', () => {
    // If `path` were a flat list of doubles these offsets would count coordinates and every
    // path would be drawn half its true length. This assertion is the guard against that.
    expect(Array.from(bundle.startIndices)).toEqual([0, 3, 5]);
    expect(bundle.startIndices).toHaveLength(bundle.length + 1);
  });

  it('exposes positions as one interleaved lon/lat buffer', () => {
    expect(bundle.positions).toBeInstanceOf(Float64Array);
    expect(bundle.positions).toHaveLength(bundle.vertexCount * 2);
    expect(Array.from(bundle.positions.slice(0, 4))).toEqual([121.0, 14.5, 121.1, 14.6]);
    // Longitude first: the reverse would put every Philippine position in Somalia.
    expect(bundle.positions[0]).toBeGreaterThan(bundle.positions[1] as number);
  });

  it('carries one timestamp per vertex, sharing the path offsets', () => {
    expect(bundle.timestamps).toHaveLength(bundle.vertexCount);
    expect(Array.from(bundle.timestamps)).toEqual([0, 30, 60, 10, 70]);
    expect(bundle.timeRange).toEqual([0, 70]);
  });

  it('maps the mode column onto the numeric attribute the GPU filters on', () => {
    expect(Array.from(bundle.modes)).toEqual([MODE_AIR, MODE_SEA]);
  });

  it('keeps labels as Arrow bytes, readable per feature on demand', () => {
    expect(readString(bundle.labels, 0)).toBe('PR123');
    expect(readString(bundle.entityIds, 1)).toBe('548123456');
    expect(readString(bundle.labels, 99)).toBe('');
  });

  it('decodes an empty artifact as nothing rather than as an error', () => {
    // A quiet window and a failed collection both produce this, and both must render blank.
    const empty = decodeTracks(tracksIPC([]));
    expect(empty.length).toBe(0);
    expect(empty.vertexCount).toBe(0);
    expect(Array.from(empty.startIndices)).toEqual([0]);
    expect(empty.timeRange).toEqual([0, 0]);
  });

  it('refuses an artifact whose geometry column is absent', () => {
    const table = new Table({ mode: vectorFromArray(['air'], new Utf8()) });
    expect(() => decodeTracks(bufferOf(tableToIPC(table, 'file')))).toThrow(/path or timestamps/);
  });
});

describe('decodePoints', () => {
  const bundle = decodePoints(
    pointsIPC([
      { mode: 'sea', entityId: '548999', label: 'MV SOLO', lon: 122.5, lat: 10.5, t: 5 },
      { mode: 'air', entityId: 'bb2222', label: '', lon: 123.5, lat: 11.5, t: 45 },
    ]),
  );

  it('reads interleaved positions from the fixed-size list child', () => {
    expect(Array.from(bundle.positions)).toEqual([122.5, 10.5, 123.5, 11.5]);
    expect(bundle.length).toBe(2);
  });

  it('reads one timestamp per point', () => {
    expect(Array.from(bundle.timestamps)).toEqual([5, 45]);
    expect(bundle.timeRange).toEqual([5, 45]);
  });

  it('distinguishes vessels from aircraft', () => {
    expect(Array.from(bundle.modes)).toEqual([MODE_SEA, MODE_AIR]);
  });

  it('treats an unreported label as empty rather than as the string "null"', () => {
    expect(readString(bundle.labels, 1)).toBe('');
  });

  it('decodes an empty artifact as nothing', () => {
    const empty = decodePoints(pointsIPC([]));
    expect(empty.length).toBe(0);
    expect(empty.positions).toHaveLength(0);
  });
});
