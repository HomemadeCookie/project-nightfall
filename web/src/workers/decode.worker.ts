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

/** `ARROW1\0\0`, the first bytes of every Arrow IPC file. */
const ARROW_MAGIC = Uint8Array.of(0x41, 0x52, 0x52, 0x4f, 0x57, 0x31, 0x00, 0x00);

function isArrowFile(buffer: ArrayBuffer): boolean {
  if (buffer.byteLength < ARROW_MAGIC.length) return false;
  const head = new Uint8Array(buffer, 0, ARROW_MAGIC.length);
  return ARROW_MAGIC.every((byte, index) => head[index] === byte);
}

async function fetchArtifact(url: string): Promise<ArrayBuffer> {
  const response = await fetch(url, { cache: 'force-cache' });
  if (!response.ok) {
    throw new Error(`artifact ${url} responded ${response.status} ${response.statusText}`);
  }
  const buffer = await response.arrayBuffer();
  // A static host answers a missing file with a page rather than an error, so an HTTP 200 is
  // not evidence that this is an artifact. Checking the magic turns that into a sentence about
  // the URL, instead of the Arrow reader reporting the first four bytes of HTML as a length.
  if (!isArrowFile(buffer)) {
    throw new Error(
      `artifact ${url} is not an Arrow IPC file. The serving set may not be published ` +
        'alongside the app at the expected path.',
    );
  }
  return buffer;
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
