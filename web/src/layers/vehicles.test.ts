import { describe, expect, it } from 'vitest';

import { MODE_AIR, MODE_SEA, type TracksBundle } from '../workers/bundles';
import {
  allocateVehicleBuffers,
  bearingDegrees,
  headAlongTrack,
  writeTrackHeads,
} from './vehicles';

const EMPTY_STRINGS = { data: new Uint8Array(0), offsets: new Int32Array(1) };

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

describe('bearingDegrees', () => {
  it('is 90 degrees for a step due east on the equator', () => {
    expect(bearingDegrees(0, 0, 1, 0)).toBeCloseTo(90, 0);
  });
});

describe('headAlongTrack', () => {
  const start = 0;
  const end = 3;

  it('is hidden before the first fix', () => {
    expect(headAlongTrack(TRACKS.positions, TRACKS.timestamps, start, end, -1, false)).toBeNull();
  });

  it('interpolates halfway along the first segment', () => {
    const head = headAlongTrack(TRACKS.positions, TRACKS.timestamps, start, end, 15, false);
    expect(head).not.toBeNull();
    expect(head?.lon).toBeCloseTo(121.05, 5);
    expect(head?.lat).toBeCloseTo(14.55, 5);
  });

  it('sits on the last fix once the playhead is past the path', () => {
    const head = headAlongTrack(TRACKS.positions, TRACKS.timestamps, start, end, 120, false);
    expect(head?.lon).toBeCloseTo(121.2, 5);
    expect(head?.lat).toBeCloseTo(14.7, 5);
  });

  it('hides a faded trip while the clock is playing', () => {
    expect(
      headAlongTrack(TRACKS.positions, TRACKS.timestamps, start, end, 400, true, 240),
    ).toBeNull();
  });
});

describe('writeTrackHeads', () => {
  it('writes one icon per path and hides paths the playhead has not reached', () => {
    const buffers = allocateVehicleBuffers(TRACKS.length);
    writeTrackHeads(TRACKS, 15, false, buffers);
    expect(buffers.positions[0]).toBeCloseTo(121.05, 5);
    expect(buffers.filters[0]).toBe(MODE_AIR);
    expect(buffers.filters[2]).toBe(MODE_SEA);
    // The vessel starts at t=10, so it is visible; the filter time stays inside the range.
    expect(buffers.filters[3]).toBeLessThanOrEqual(15);
  });
});
