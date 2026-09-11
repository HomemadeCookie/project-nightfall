/**
 * The wire format between the decode worker and the main thread.
 *
 * Everything numeric is a typed array whose `ArrayBuffer` is transferred, not copied. The
 * geometry buffers go straight into deck.gl's binary attribute form, which is the whole point
 * of invariant 4: between the bake stage and the GPU nothing parses geometry.
 *
 * Labels travel as Arrow's own string layout — a UTF-8 byte buffer plus offsets — rather than
 * as a JavaScript string array. A track set large enough to matter would otherwise mean tens
 * of thousands of string allocations on load to serve text that is only ever read on hover.
 */

/** Aircraft and vessels are distinguished numerically so the mode can drive a GPU attribute. */
export const MODE_AIR = 0;
export const MODE_SEA = 1;

export interface StringColumn {
  /** UTF-8 bytes of every value, concatenated. */
  data: Uint8Array;
  /** `length + 1` byte offsets into `data`. */
  offsets: Int32Array;
}

export interface TracksBundle {
  readonly kind: 'tracks';
  /** Number of paths. */
  length: number;
  /** `length + 1` vertex offsets: deck.gl's `startIndices`, already counted in vertices. */
  startIndices: Int32Array;
  /** Interleaved lon/lat, two doubles per vertex. */
  positions: Float64Array;
  /** One value per vertex, seconds relative to the artifact epoch. */
  timestamps: Float32Array;
  /** One value per path. */
  modes: Uint8Array;
  entityIds: StringColumn;
  labels: StringColumn;
  /** Earliest and latest timestamp present, in artifact seconds. */
  timeRange: readonly [number, number];
  vertexCount: number;
}

export interface PointsBundle {
  readonly kind: 'points';
  length: number;
  /** Interleaved lon/lat, two doubles per point. */
  positions: Float64Array;
  timestamps: Float32Array;
  modes: Uint8Array;
  entityIds: StringColumn;
  labels: StringColumn;
  timeRange: readonly [number, number];
}

export type Bundle = TracksBundle | PointsBundle;

const DECODER = new TextDecoder();

/** Read one value out of a string column. Called on hover, not on load. */
export function readString(column: StringColumn, index: number): string {
  const start = column.offsets[index];
  const end = column.offsets[index + 1];
  if (start === undefined || end === undefined || end <= start) return '';
  return DECODER.decode(column.data.subarray(start, end));
}

/** Every transferable buffer in a bundle, for Comlink's transfer list. */
export function transferables(bundle: Bundle): Transferable[] {
  const shared: Transferable[] = [
    bundle.positions.buffer as ArrayBuffer,
    bundle.timestamps.buffer as ArrayBuffer,
    bundle.modes.buffer as ArrayBuffer,
    bundle.entityIds.data.buffer as ArrayBuffer,
    bundle.entityIds.offsets.buffer as ArrayBuffer,
    bundle.labels.data.buffer as ArrayBuffer,
    bundle.labels.offsets.buffer as ArrayBuffer,
  ];
  if (bundle.kind === 'tracks') {
    shared.push(bundle.startIndices.buffer as ArrayBuffer);
  }
  // A zero-length column can share one empty buffer, and a buffer may only be transferred
  // once, so duplicates are removed rather than throwing a DataCloneError.
  return [...new Set(shared)];
}
