/**
 * Vehicle markers on top of the mobility overlay.
 *
 * Track paths stay binary and only receive a `currentTime` uniform. These icons have to
 * move, so their positions are written into reused typed arrays each tick — one lon/lat and
 * one heading per path, not a geometry rebuild. Isolated sightings use the baked point
 * buffer as-is.
 *
 * Icons are drawn on a canvas atlas rather than loaded from a host: a third-party icon
 * font or CDN would be a third-party request (invariant 1).
 */

import type { Layer as DeckLayer } from '@deck.gl/core';
import { DataFilterExtension } from '@deck.gl/extensions';
import { IconLayer } from '@deck.gl/layers';

import { TRAIL_LENGTH_S } from '../config';
import { MODE_AIR, MODE_SEA, type TracksBundle } from '../workers/bundles';
import { AIR_COLOUR, SEA_COLOUR } from './mobility';

const MODE_TIME_FILTER = new DataFilterExtension({ filterSize: 2 });

const ICON_SIZE_PX = 64;
const HIDDEN_TIME_OFFSET = 1_000_000;

export interface VehicleBuffers {
  positions: Float64Array;
  angles: Float32Array;
  filters: Float32Array;
}

export function allocateVehicleBuffers(count: number): VehicleBuffers {
  return {
    positions: new Float64Array(count * 2),
    angles: new Float32Array(count),
    filters: new Float32Array(count * 2),
  };
}

/** Geographic bearing, degrees clockwise from north. */
export function bearingDegrees(lon1: number, lat1: number, lon2: number, lat2: number): number {
  const phi1 = (lat1 * Math.PI) / 180;
  const phi2 = (lat2 * Math.PI) / 180;
  const dLambda = ((lon2 - lon1) * Math.PI) / 180;
  const y = Math.sin(dLambda) * Math.cos(phi2);
  const x = Math.cos(phi1) * Math.sin(phi2) - Math.sin(phi1) * Math.cos(phi2) * Math.cos(dLambda);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

/**
 * Interpolate one path to `currentTime`.
 *
 * Returns null when the playhead has not reached the path, or — while playing — when the
 * trail has already faded past the last fix. A paused clock keeps the marker at the last
 * observed point so a scrubber parked at the end of the window still shows every vehicle.
 */
export function headAlongTrack(
  positions: Float64Array,
  timestamps: Float32Array,
  start: number,
  end: number,
  currentTime: number,
  playing: boolean,
  trailLengthS: number = TRAIL_LENGTH_S,
): { lon: number; lat: number; angle: number } | null {
  if (end - start < 1) return null;
  const last = end - 1;
  const firstT = timestamps[start] ?? 0;
  const lastT = timestamps[last] ?? firstT;
  if (currentTime < firstT) return null;
  if (playing && currentTime > lastT + trailLengthS) return null;

  let lo = start;
  while (lo + 1 < end && (timestamps[lo + 1] ?? 0) <= currentTime) {
    lo += 1;
  }
  const hi = Math.min(lo + 1, last);
  const t0 = timestamps[lo] ?? 0;
  const t1 = timestamps[hi] ?? t0;
  const lon0 = positions[lo * 2] ?? 0;
  const lat0 = positions[lo * 2 + 1] ?? 0;
  const lon1 = positions[hi * 2] ?? lon0;
  const lat1 = positions[hi * 2 + 1] ?? lat0;

  let lon = lon0;
  let lat = lat0;
  if (hi > lo && t1 > t0 && currentTime < lastT) {
    const u = (currentTime - t0) / (t1 - t0);
    lon = lon0 + (lon1 - lon0) * u;
    lat = lat0 + (lat1 - lat0) * u;
  } else if (currentTime >= lastT) {
    lon = positions[last * 2] ?? lon0;
    lat = positions[last * 2 + 1] ?? lat0;
  }

  let fromLon = lon0;
  let fromLat = lat0;
  let toLon = lon1;
  let toLat = lat1;
  if (hi === lo && lo > start) {
    fromLon = positions[(lo - 1) * 2] ?? lon0;
    fromLat = positions[(lo - 1) * 2 + 1] ?? lat0;
    toLon = lon0;
    toLat = lat0;
  }
  return { lon, lat, angle: bearingDegrees(fromLon, fromLat, toLon, toLat) };
}

/** Write one icon per path into `into`. Hidden paths keep a filter timestamp outside the range. */
export function writeTrackHeads(
  bundle: TracksBundle,
  currentTime: number,
  playing: boolean,
  into: VehicleBuffers,
): void {
  for (let path = 0; path < bundle.length; path += 1) {
    const start = bundle.startIndices[path] ?? 0;
    const end = bundle.startIndices[path + 1] ?? start;
    const mode = bundle.modes[path] ?? MODE_AIR;
    const head = headAlongTrack(
      bundle.positions,
      bundle.timestamps,
      start,
      end,
      currentTime,
      playing,
    );
    into.filters[path * 2] = mode;
    if (head === null) {
      into.filters[path * 2 + 1] = currentTime + HIDDEN_TIME_OFFSET;
      continue;
    }
    into.positions[path * 2] = head.lon;
    into.positions[path * 2 + 1] = head.lat;
    into.angles[path] = head.angle;
    into.filters[path * 2 + 1] = Math.min(currentTime, bundle.timestamps[end - 1] ?? currentTime);
  }
}

export function pointAngles(count: number): Float32Array {
  return new Float32Array(count);
}

let atlasUrl: string | null = null;

function vehicleAtlas(): string {
  if (atlasUrl !== null) return atlasUrl;
  const canvas = document.createElement('canvas');
  canvas.width = ICON_SIZE_PX * 2;
  canvas.height = ICON_SIZE_PX;
  const ctx = canvas.getContext('2d');
  if (ctx === null) {
    throw new Error('vehicle icons need a 2D canvas');
  }
  drawPlane(ctx, ICON_SIZE_PX / 2, ICON_SIZE_PX / 2);
  drawShip(ctx, ICON_SIZE_PX + ICON_SIZE_PX / 2, ICON_SIZE_PX / 2);
  atlasUrl = canvas.toDataURL('image/png');
  return atlasUrl;
}

function drawPlane(ctx: CanvasRenderingContext2D, cx: number, cy: number): void {
  ctx.save();
  ctx.translate(cx, cy);
  ctx.fillStyle = '#ffffff';
  ctx.beginPath();
  ctx.moveTo(0, -26);
  ctx.lineTo(3.5, 6);
  ctx.lineTo(2, 22);
  ctx.lineTo(-2, 22);
  ctx.lineTo(-3.5, 6);
  ctx.closePath();
  ctx.fill();
  ctx.beginPath();
  ctx.moveTo(-26, 0);
  ctx.lineTo(26, 0);
  ctx.lineTo(7, 7);
  ctx.lineTo(-7, 7);
  ctx.closePath();
  ctx.fill();
  ctx.beginPath();
  ctx.moveTo(-11, 16);
  ctx.lineTo(11, 16);
  ctx.lineTo(3, 22);
  ctx.lineTo(-3, 22);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function drawShip(ctx: CanvasRenderingContext2D, cx: number, cy: number): void {
  ctx.save();
  ctx.translate(cx, cy);
  ctx.fillStyle = '#ffffff';
  ctx.beginPath();
  ctx.moveTo(0, -26);
  ctx.lineTo(10, -10);
  ctx.lineTo(12, 16);
  ctx.lineTo(6, 24);
  ctx.lineTo(-6, 24);
  ctx.lineTo(-12, 16);
  ctx.lineTo(-10, -10);
  ctx.closePath();
  ctx.fill();
  ctx.fillRect(-5, -4, 10, 16);
  ctx.restore();
}

const ICON_MAPPING = {
  plane: { x: 0, y: 0, width: ICON_SIZE_PX, height: ICON_SIZE_PX, mask: true },
  ship: { x: ICON_SIZE_PX, y: 0, width: ICON_SIZE_PX, height: ICON_SIZE_PX, mask: true },
};

export interface VehicleLayerOptions {
  id: string;
  length: number;
  positions: Float64Array;
  angles: Float32Array;
  modes: Uint8Array;
  filters: Float32Array;
  range: [[number, number], [number, number]] | null;
  currentTime: number;
}

export function vehicleLayer(options: VehicleLayerOptions): DeckLayer {
  const { length, positions, angles, modes, filters, range } = options;
  return new IconLayer({
    id: options.id,
    visible: range !== null && length > 0,
    data: {
      length,
      attributes: {
        getPosition: { value: positions, size: 2 },
        getAngle: { value: angles, size: 1 },
        getFilterValue: { value: filters, size: 2 },
      },
    },
    iconAtlas: vehicleAtlas(),
    iconMapping: ICON_MAPPING,
    getIcon: (_: unknown, info: { index: number }) =>
      modes[info.index] === MODE_SEA ? 'ship' : 'plane',
    getColor: (_: unknown, info: { index: number }) =>
      modes[info.index] === MODE_SEA ? SEA_COLOUR : AIR_COLOUR,
    extensions: [MODE_TIME_FILTER],
    filterRange: range ?? [
      [MODE_AIR, MODE_SEA],
      [Number.NEGATIVE_INFINITY, Number.POSITIVE_INFINITY],
    ],
    sizeUnits: 'pixels',
    getSize: 18,
    // Stay readable when the map is pulled back to the whole archipelago.
    sizeMinPixels: 14,
    sizeMaxPixels: 28,
    billboard: true,
    pickable: true,
    updateTriggers: {
      getPosition: options.currentTime,
      getAngle: options.currentTime,
    },
  }) as unknown as DeckLayer;
}
