/**
 * Arrow IPC to deck.gl binary attributes, with no intermediate representation.
 *
 * Kept separate from the worker entry point so it can be tested directly: a layout mistake
 * here does not raise, it silently shifts every vertex offset and the map draws confident
 * nonsense. `pipeline/tests/test_artifacts.py` pins the producing side of the same contract.
 */
import { type Data, type Table, tableFromIPC } from 'apache-arrow';

import {
  MODE_AIR,
  MODE_SEA,
  type PointsBundle,
  type StringColumn,
  type TracksBundle,
} from './bundles';

const EMPTY_STRINGS: StringColumn = { data: new Uint8Array(0), offsets: new Int32Array(1) };

function stringColumn(table: Table, name: string): StringColumn {
  const column = table.getChild(name);
  if (column === null || table.numRows === 0) return EMPTY_STRINGS;
  const chunk = column.data[0];
  if (chunk === undefined) return EMPTY_STRINGS;
  // Arrow already stores strings as a UTF-8 byte buffer plus offsets, which is exactly what
  // travels to the main thread. Nothing is decoded until something is hovered.
  const data = chunk.values as Uint8Array;
  const offsets = chunk.valueOffsets as Int32Array;
  return { data: data.slice(), offsets: offsets.slice(0, table.numRows + 1) };
}

function modeColumn(table: Table): Uint8Array {
  const column = table.getChild('mode');
  const modes = new Uint8Array(table.numRows);
  if (column === null) return modes;
  for (let index = 0; index < table.numRows; index += 1) {
    modes[index] = column.get(index) === 'sea' ? MODE_SEA : MODE_AIR;
  }
  return modes;
}

/**
 * Reject a sliced or multi-batch column instead of misreading it.
 *
 * Arrow applies `offset` at access time, so reading a buffer directly is only valid at offset
 * zero. The bake stage writes one record batch per artifact, so this never fires in practice —
 * and if a future change makes it fire, a loud failure is the right outcome, because the
 * alternative is every vertex silently shifted by a constant.
 */
function requireWholeBuffer(data: Data, column: string): void {
  if (data.offset !== 0) {
    throw new Error(`${column} column is offset into a larger buffer, which is not supported`);
  }
}

/**
 * The interleaved coordinate buffer under a `fixed_size_list<double>[2]`.
 *
 * The floats live one level below the list node: the list itself carries no value buffer, only
 * its child does. Reading the list node's own `values` yields undefined, which is how a whole
 * layer becomes empty without an error.
 */
function interleavedPositions(list: Data, vertices: number, column: string): Float64Array {
  requireWholeBuffer(list, column);
  const child = list.children[0];
  if (child === undefined) {
    throw new Error(`${column} column has no coordinate child`);
  }
  requireWholeBuffer(child, column);
  const values = child.values as Float64Array;
  if (values.length < vertices * 2) {
    throw new Error(
      `${column} column holds ${values.length} coordinates, short of the ` +
        `${vertices * 2} its offsets describe`,
    );
  }
  return values.slice(0, vertices * 2);
}

function range(values: Float32Array): readonly [number, number] {
  if (values.length === 0) return [0, 0];
  let low = Number.POSITIVE_INFINITY;
  let high = Number.NEGATIVE_INFINITY;
  for (const value of values) {
    if (value < low) low = value;
    if (value > high) high = value;
  }
  return [low, high];
}

export function decodeTracks(payload: ArrayBuffer): TracksBundle {
  const table = tableFromIPC(payload);
  const pathColumn = table.getChild('path');
  const stampColumn = table.getChild('timestamps');

  if (pathColumn === null || stampColumn === null) {
    throw new Error('tracks artifact is missing its path or timestamps column');
  }

  const pathChunk = pathColumn.data[0];
  const stampChunk = stampColumn.data[0];

  // An empty artifact is a legitimate state — a quiet window, or a failed collection — and
  // must render as nothing rather than as an error.
  if (table.numRows === 0 || pathChunk === undefined || stampChunk === undefined) {
    return {
      kind: 'tracks',
      length: 0,
      startIndices: new Int32Array(1),
      positions: new Float64Array(0),
      timestamps: new Float32Array(0),
      modes: new Uint8Array(0),
      entityIds: EMPTY_STRINGS,
      labels: EMPTY_STRINGS,
      timeRange: [0, 0],
      vertexCount: 0,
    };
  }

  // `path` is list<fixed_size_list<double>[2]>, so these offsets count *vertices* — deck.gl's
  // `startIndices` — rather than coordinates. A flat list of doubles would make the offsets
  // count coordinates and draw every path at half its true length.
  requireWholeBuffer(pathChunk, 'path');
  const startIndices = (pathChunk.valueOffsets as Int32Array).slice(0, table.numRows + 1);
  const vertexCount = startIndices[table.numRows] ?? 0;

  const pointList = pathChunk.children[0];
  if (pointList === undefined) {
    throw new Error('tracks artifact path column has no point child');
  }
  const positions = interleavedPositions(pointList, vertexCount, 'path');

  // Timestamps are list<float32> over the same offsets, so one value per vertex.
  requireWholeBuffer(stampChunk, 'timestamps');
  const stampChild = stampChunk.children[0];
  if (stampChild === undefined) {
    throw new Error('tracks artifact timestamps column has no value child');
  }
  requireWholeBuffer(stampChild, 'timestamps');
  const timestamps = (stampChild.values as Float32Array).slice(0, vertexCount);

  return {
    kind: 'tracks',
    length: table.numRows,
    startIndices,
    positions,
    timestamps,
    modes: modeColumn(table),
    entityIds: stringColumn(table, 'entity_id'),
    labels: stringColumn(table, 'label'),
    timeRange: range(timestamps),
    vertexCount,
  };
}

export function decodePoints(payload: ArrayBuffer): PointsBundle {
  const table = tableFromIPC(payload);
  const positionColumn = table.getChild('position');
  const stampColumn = table.getChild('timestamp');

  if (positionColumn === null || stampColumn === null) {
    throw new Error('points artifact is missing its position or timestamp column');
  }

  const positionChunk = positionColumn.data[0];
  if (table.numRows === 0 || positionChunk === undefined) {
    return {
      kind: 'points',
      length: 0,
      positions: new Float64Array(0),
      timestamps: new Float32Array(0),
      modes: new Uint8Array(0),
      entityIds: EMPTY_STRINGS,
      labels: EMPTY_STRINGS,
      timeRange: [0, 0],
    };
  }

  // `position` is fixed_size_list<double>[2], so the interleaved array is its child buffer.
  const positions = interleavedPositions(positionChunk, table.numRows, 'position');
  const timestamps = new Float32Array(table.numRows);
  for (let index = 0; index < table.numRows; index += 1) {
    timestamps[index] = stampColumn.get(index) ?? 0;
  }

  return {
    kind: 'points',
    length: table.numRows,
    positions,
    timestamps,
    modes: modeColumn(table),
    entityIds: stringColumn(table, 'entity_id'),
    labels: stringColumn(table, 'label'),
    timeRange: range(timestamps),
  };
}
