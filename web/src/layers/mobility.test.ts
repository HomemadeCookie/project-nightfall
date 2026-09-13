import { describe, expect, it } from 'vitest';

import { MODE_AIR, MODE_SEA, type PointsBundle, type TracksBundle } from '../workers/bundles';
import {
  AIR_COLOUR,
  filterRange,
  pointColours,
  pointFilters,
  pointModes,
  SEA_COLOUR,
  timeFilterRange,
  vertexColours,
  vertexFilters,
  vertexModes,
} from './mobility';

const EMPTY_STRINGS = { data: new Uint8Array(0), offsets: new Int32Array(1) };

/** Two paths: an aircraft of three vertices, then a vessel of two. */
const TRACKS: TracksBundle = {
  kind: 'tracks',
  length: 2,
  startIndices: new Int32Array([0, 3, 5]),
  positions: new Float64Array([121, 14.5, 121.1, 14.6, 121.2, 14.7, 120.9, 14.4, 120.95, 14.45]),
  timestamps: new Float32Array([0, 30, 60, 10, 70]),
  modes: new Uint8Array([MODE_AIR, MODE_SEA]),
  entityIds: EMPTY_STRINGS,
  labels: EMPTY_STRINGS,
  timeRange: [0, 70],
  vertexCount: 5,
};

const POINTS: PointsBundle = {
  kind: 'points',
  length: 2,
  positions: new Float64Array([122.5, 10.5, 123.5, 11.5]),
  timestamps: new Float32Array([5, 45]),
  modes: new Uint8Array([MODE_SEA, MODE_AIR]),
  entityIds: EMPTY_STRINGS,
  labels: EMPTY_STRINGS,
  timeRange: [5, 45],
};

describe('vertexColours', () => {
  it('expands a per-path mode across that path\u2019s vertices', () => {
    const colours = vertexColours(TRACKS);
    expect(colours).toHaveLength(TRACKS.vertexCount * 3);
    // First three vertices belong to the aircraft, the last two to the vessel.
    expect(Array.from(colours.slice(0, 3))).toEqual(AIR_COLOUR);
    expect(Array.from(colours.slice(6, 9))).toEqual(AIR_COLOUR);
    expect(Array.from(colours.slice(9, 12))).toEqual(SEA_COLOUR);
    expect(Array.from(colours.slice(12, 15))).toEqual(SEA_COLOUR);
  });
});

describe('vertexModes', () => {
  it('produces one filter value per vertex, aligned with the path offsets', () => {
    expect(Array.from(vertexModes(TRACKS))).toEqual([
      MODE_AIR,
      MODE_AIR,
      MODE_AIR,
      MODE_SEA,
      MODE_SEA,
    ]);
  });

  it('handles an empty bundle without producing a stray vertex', () => {
    const empty: TracksBundle = { ...TRACKS, length: 0, vertexCount: 0 };
    expect(vertexModes(empty)).toHaveLength(0);
  });
});

describe('pointColours and pointModes', () => {
  it('colours and tags each point by its own mode', () => {
    expect(Array.from(pointColours(POINTS).slice(0, 3))).toEqual(SEA_COLOUR);
    expect(Array.from(pointColours(POINTS).slice(3, 6))).toEqual(AIR_COLOUR);
    expect(Array.from(pointModes(POINTS))).toEqual([MODE_SEA, MODE_AIR]);
  });
});

describe('filterRange', () => {
  it('covers both modes when both are shown', () => {
    expect(filterRange(true, true)).toEqual([MODE_AIR, MODE_SEA]);
  });

  it('narrows to a single mode, inclusive of itself', () => {
    expect(filterRange(true, false)).toEqual([MODE_AIR, MODE_AIR]);
    expect(filterRange(false, true)).toEqual([MODE_SEA, MODE_SEA]);
  });

  it('reports nothing selected rather than an empty range', () => {
    // An empty range would still cost a draw call per artifact; the caller turns null into an
    // invisible layer instead.
    expect(filterRange(false, false)).toBeNull();
  });
});

describe('timeFilterRange', () => {
  it('clips the selected span onto the mode range', () => {
    expect(timeFilterRange([0, 1], 10, 40)).toEqual([
      [0, 1],
      [10, 40],
    ]);
  });

  it('stays hidden when no mode is selected', () => {
    expect(timeFilterRange(null, 0, 10)).toBeNull();
  });
});

describe('vertexFilters', () => {
  it('interleaves mode and timestamp so a range change is a uniform', () => {
    const modes = vertexModes(TRACKS);
    const filters = vertexFilters(modes, TRACKS.timestamps);
    expect(Array.from(filters.slice(0, 4))).toEqual([MODE_AIR, 0, MODE_AIR, 30]);
    expect(Array.from(filters.slice(6, 10))).toEqual([MODE_SEA, 10, MODE_SEA, 70]);
  });
});

describe('pointFilters', () => {
  it('pairs each isolated fix with its own time', () => {
    expect(Array.from(pointFilters(pointModes(POINTS), POINTS.timestamps))).toEqual([
      MODE_SEA,
      5,
      MODE_AIR,
      45,
    ]);
  });
});
