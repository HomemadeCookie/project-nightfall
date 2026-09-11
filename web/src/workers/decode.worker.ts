/**
 * Fetch and decode, off the main thread.
 *
 * Every artifact byte enters the app here. The main thread is left free for the single
 * animation loop (`.cursorrules` § 6), and the decoded buffers are transferred rather than
 * copied, so a large track set costs one message rather than a heap spike.
 */
import * as Comlink from 'comlink';

import { type Bundle, transferables } from './bundles';
import { decodePoints, decodeTracks } from './decode';

async function fetchArtifact(url: string): Promise<ArrayBuffer> {
  const response = await fetch(url, { cache: 'force-cache' });
  if (!response.ok) {
    throw new Error(`artifact ${url} responded ${response.status} ${response.statusText}`);
  }
  return response.arrayBuffer();
}

const api = {
  async loadTracks(url: string): Promise<Bundle> {
    const bundle = decodeTracks(await fetchArtifact(url));
    return Comlink.transfer(bundle, transferables(bundle));
  },

  async loadPoints(url: string): Promise<Bundle> {
    const bundle = decodePoints(await fetchArtifact(url));
    return Comlink.transfer(bundle, transferables(bundle));
  },
};

export type DecodeApi = typeof api;

Comlink.expose(api);
