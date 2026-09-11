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

/**
 * Resolve an artifact URL against the page before it crosses into the worker.
 *
 * A worker resolves a relative URL against its own script URL, not the document's, so the
 * manifest's relative paths would be fetched from wherever the bundler happened to emit the
 * worker. That request succeeds — a static host answers a miss with its own HTML — and the
 * failure only surfaces as an unintelligible complaint from the Arrow reader. Every URL enters
 * the worker through this module, so resolving here covers all of them.
 */
function fromPage(url: string): string {
  return new URL(url, document.baseURI).href;
}

export async function loadTracks(url: string): Promise<TracksBundle> {
  return assertKind(await api().loadTracks(fromPage(url)), 'tracks') as TracksBundle;
}

export async function loadPoints(url: string): Promise<PointsBundle> {
  return assertKind(await api().loadPoints(fromPage(url)), 'points') as PointsBundle;
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
