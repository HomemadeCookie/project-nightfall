/**
 * The mobility overlay.
 *
 * Three rules are structural here rather than advisory.
 *
 * Invariant 4: the layers are handed deck.gl's binary attribute form directly, built from the
 * Arrow buffers the worker transferred. There is no `GeoJsonLayer`, no accessor function per
 * feature, and nothing on this path parses geometry.
 *
 * `.cursorrules` § 6: animation advances a `currentTime` uniform on `TripsLayer`. The `data`
 * prop is built once per artifact and never mutated per frame, so a tick costs a uniform
 * write rather than a buffer upload.
 *
 * WebGL2 only. The WebGPU backend is excluded because it does not support picking, and
 * hover is how a track reveals what it is.
 */

import type { Layer as DeckLayer } from '@deck.gl/core';
import { DataFilterExtension } from '@deck.gl/extensions';
import { TripsLayer } from '@deck.gl/geo-layers';
import { ScatterplotLayer } from '@deck.gl/layers';

import { TRAIL_LENGTH_S } from '../config';
import { MODE_AIR, MODE_SEA, type PointsBundle, type TracksBundle } from '../workers/bundles';

/** One instance, shared by every layer: mode + time, so a range change is a uniform. */
const MODE_TIME_FILTER = new DataFilterExtension({ filterSize: 2 });

/** Aircraft and vessels are told apart by colour, not by being in different layers. */
export const AIR_COLOUR: [number, number, number] = [255, 176, 59];
export const SEA_COLOUR: [number, number, number] = [86, 204, 242];

/**
 * Per-vertex colours, expanded once from the per-path mode.
 *
 * deck.gl accepts a constant or a per-object accessor, but a binary path layer wants a flat
 * per-vertex buffer, and building it here means the GPU never sees a callback.
 */
export function vertexColours(bundle: TracksBundle): Uint8Array {
  const colours = new Uint8Array(bundle.vertexCount * 3);
  for (let path = 0; path < bundle.length; path += 1) {
    const start = bundle.startIndices[path] ?? 0;
    const end = bundle.startIndices[path + 1] ?? start;
    const colour = bundle.modes[path] === MODE_SEA ? SEA_COLOUR : AIR_COLOUR;
    for (let vertex = start; vertex < end; vertex += 1) {
      colours[vertex * 3] = colour[0];
      colours[vertex * 3 + 1] = colour[1];
      colours[vertex * 3 + 2] = colour[2];
    }
  }
  return colours;
}

/**
 * Per-vertex mode, as the filter attribute.
 *
 * Hiding aircraft or vessels is a GPU filter, not a rebuild: one artifact holds both, and
 * re-deriving separate buffers per toggle would re-upload every position to hide half of
 * them. `DataFilterExtension` discards the filtered vertices in the vertex shader, so they
 * cost nothing to draw and cannot be picked either.
 */
export function vertexModes(bundle: TracksBundle): Float32Array {
  const modes = new Float32Array(bundle.vertexCount);
  for (let path = 0; path < bundle.length; path += 1) {
    const start = bundle.startIndices[path] ?? 0;
    const end = bundle.startIndices[path + 1] ?? start;
    const mode = bundle.modes[path] ?? MODE_AIR;
    modes.fill(mode, start, end);
  }
  return modes;
}

export function pointModes(bundle: PointsBundle): Float32Array {
  return Float32Array.from(bundle.modes);
}

/**
 * Which modes to draw, as a filter range over `MODE_AIR`/`MODE_SEA`.
 *
 * Returns `null` when nothing is selected, which the caller turns into an invisible layer —
 * an empty range would still cost a draw call per artifact.
 */
export function filterRange(showAir: boolean, showSea: boolean): [number, number] | null {
  if (showAir && showSea) return [MODE_AIR, MODE_SEA];
  if (showAir) return [MODE_AIR, MODE_AIR];
  if (showSea) return [MODE_SEA, MODE_SEA];
  return null;
}

/**
 * Interleave per-vertex mode and timestamp for a two-channel GPU filter.
 *
 * Channel 0 hides a mode; channel 1 clips the selected range so a playhead parked at 18:00
 * inside a 08:00–18:00 selection does not keep drawing the 03:00 tracks.
 */
export function vertexFilters(modes: Float32Array, timestamps: Float32Array): Float32Array {
  const filters = new Float32Array(modes.length * 2);
  for (let index = 0; index < modes.length; index += 1) {
    filters[index * 2] = modes[index] ?? MODE_AIR;
    filters[index * 2 + 1] = timestamps[index] ?? 0;
  }
  return filters;
}

export function pointFilters(modes: Float32Array, timestamps: Float32Array): Float32Array {
  return vertexFilters(modes, timestamps);
}

export function timeFilterRange(
  modeRange: [number, number] | null,
  start: number,
  end: number,
): [[number, number], [number, number]] | null {
  if (modeRange === null) return null;
  return [modeRange, [start, end]];
}

export function pointColours(bundle: PointsBundle): Uint8Array {
  const colours = new Uint8Array(bundle.length * 3);
  for (let index = 0; index < bundle.length; index += 1) {
    const colour = bundle.modes[index] === MODE_SEA ? SEA_COLOUR : AIR_COLOUR;
    colours[index * 3] = colour[0];
    colours[index * 3 + 1] = colour[1];
    colours[index * 3 + 2] = colour[2];
  }
  return colours;
}

export interface TrackLayerOptions {
  id: string;
  bundle: TracksBundle;
  colours: Uint8Array;
  filters: Float32Array;
  range: [[number, number], [number, number]] | null;
  currentTime: number;
  /** Whether the clock is running, which is what the trail is for. */
  playing: boolean;
}

export function trackLayer(options: TrackLayerOptions): DeckLayer {
  const { bundle, colours, range } = options;
  return new TripsLayer({
    id: options.id,
    visible: range !== null && bundle.length > 0,
    data: {
      length: bundle.length,
      startIndices: bundle.startIndices,
      attributes: {
        getPath: { value: bundle.positions, size: 2 },
        getTimestamps: { value: bundle.timestamps, size: 1 },
        getColor: { value: colours, size: 3 },
        getFilterValue: { value: options.filters, size: 2 },
      },
    },
    extensions: [MODE_TIME_FILTER],
    filterRange: range ?? [
      [MODE_AIR, MODE_SEA],
      [Number.NEGATIVE_INFINITY, Number.POSITIVE_INFINITY],
    ],
    // Required by deck.gl's binary path form: the accessors are never called, but their
    // presence tells the layer the attributes are supplied rather than derived.
    _pathType: 'open',
    widthUnits: 'pixels',
    // A hairline reads as noise on a dark basemap and is hard to aim at; two pixels is the
    // point where a track looks deliberate without the overlay becoming the map.
    widthMinPixels: 2,
    widthMaxPixels: 4,
    capRounded: true,
    jointRounded: true,
    // The trail is the motion cue, so it only exists while there is motion. A standing clock
    // — paused, scrubbed, or a device that will not animate — draws each track whole up to the
    // playhead instead, which is both more informative and the only thing consistent with the
    // time the scrubber is displaying.
    fadeTrail: options.playing,
    trailLength: TRAIL_LENGTH_S,
    currentTime: options.currentTime,
    pickable: true,
    opacity: 0.85,
  }) as unknown as DeckLayer;
}

export interface PointLayerOptions {
  id: string;
  bundle: PointsBundle;
  colours: Uint8Array;
  filters: Float32Array;
  range: [[number, number], [number, number]] | null;
}

export function pointLayer(options: PointLayerOptions): DeckLayer {
  const { bundle, colours, range } = options;
  return new ScatterplotLayer({
    id: options.id,
    visible: range !== null && bundle.length > 0,
    data: {
      length: bundle.length,
      attributes: {
        getPosition: { value: bundle.positions, size: 2 },
        getFillColor: { value: colours, size: 3 },
        getFilterValue: { value: options.filters, size: 2 },
      },
    },
    extensions: [MODE_TIME_FILTER],
    filterRange: range ?? [
      [MODE_AIR, MODE_SEA],
      [Number.NEGATIVE_INFINITY, Number.POSITIVE_INFINITY],
    ],
    radiusUnits: 'pixels',
    getRadius: 3,
    radiusMinPixels: 2,
    radiusMaxPixels: 6,
    stroked: false,
    pickable: true,
    opacity: 0.9,
  }) as unknown as DeckLayer;
}
