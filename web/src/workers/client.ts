/**
 * One decode worker for the whole app.
 *
 * A worker per request would multiply the Arrow module across threads for no gain: artifacts
 * are fetched a handful at a time, and the work is dominated by the network rather than by
 * decoding.
 */
import * as Comlink from 'comlink';

import type { Bundle, PointsBundle, TracksBundle } from './bundles';
import type { DecodeApi } from './decode.worker';

let remote: Comlink.Remote<DecodeApi> | null = null;
let worker: Worker | null = null;

function api(): Comlink.Remote<DecodeApi> {
  if (remote === null) {
    worker = new Worker(new URL('./decode.worker.ts', import.meta.url), { type: 'module' });
    remote = Comlink.wrap<DecodeApi>(worker);
  }
  return remote;
}

export async function loadTracks(url: string): Promise<TracksBundle> {
  return assertKind(await api().loadTracks(url), 'tracks') as TracksBundle;
}

export async function loadPoints(url: string): Promise<PointsBundle> {
  return assertKind(await api().loadPoints(url), 'points') as PointsBundle;
}

function assertKind(bundle: Bundle, kind: Bundle['kind']): Bundle {
  if (bundle.kind !== kind) {
    throw new Error(`expected a ${kind} bundle, received ${bundle.kind}`);
  }
  return bundle;
}

/** Release the worker. Used by tests and by the context-loss rebuild path. */
export function terminateDecodeWorker(): void {
  worker?.terminate();
  worker = null;
  remote = null;
}
