import { createReadStream, statSync } from 'node:fs';
import { extname, join, normalize, resolve } from 'node:path';

import react from '@vitejs/plugin-react';
import type { Plugin } from 'vite';
// From `vitest/config` rather than `vite`, so the `test` block below is type-checked instead
// of merely tolerated.
import { defineConfig } from 'vitest/config';

/**
 * The app is a static bundle with no server (README § Infrastructure). `base` is relative so
 * the same build works at a GitHub Pages project path and at the root of any other free
 * static host, which is the escape hatch the manifest-of-relative-URLs design exists for.
 */

/** Where the pipeline writes its serving set, relative to this directory. */
const SERVING_DIR = resolve(import.meta.dirname, '..', 'build', 'serving');

const CONTENT_TYPES: Record<string, string> = {
  '.json': 'application/json',
  '.arrow': 'application/vnd.apache.arrow.file',
  '.pmtiles': 'application/octet-stream',
};

/**
 * Serve the pipeline's output at `/serving/*` during development.
 *
 * Read from `build/serving` rather than copied into `public/`, because data files never enter
 * the repository (`.cursorrules` § 4) and a copy would go stale the moment the pipeline ran
 * again. In production the deploy step assembles the same paths inside the built site.
 */
function servingSet(): Plugin {
  return {
    name: 'nightfall-serving-set',
    configureServer(server) {
      server.middlewares.use('/serving', (request, response, next) => {
        const relative = normalize(decodeURIComponent((request.url ?? '/').split('?')[0] ?? '/'));
        const path = join(SERVING_DIR, relative);
        // `normalize` has already collapsed any `..`, so this rejects an escape attempt
        // rather than merely discouraging one.
        if (!path.startsWith(SERVING_DIR)) {
          response.statusCode = 403;
          response.end('outside the serving set');
          return;
        }
        let size: number;
        try {
          size = statSync(path).size;
        } catch {
          next();
          return;
        }
        response.setHeader(
          'content-type',
          CONTENT_TYPES[extname(path)] ?? 'application/octet-stream',
        );
        // Range support matters: the basemap probe issues one to check PMTiles is reachable,
        // and pmtiles.js reads the archive entirely through range requests.
        response.setHeader('accept-ranges', 'bytes');
        const range = /^bytes=(\d*)-(\d*)$/.exec(request.headers.range ?? '');
        if (range) {
          const start = range[1] === '' ? 0 : Number(range[1]);
          const end = range[2] === '' ? size - 1 : Math.min(Number(range[2]), size - 1);
          response.statusCode = 206;
          response.setHeader('content-range', `bytes ${start}-${end}/${size}`);
          response.setHeader('content-length', String(end - start + 1));
          createReadStream(path, { start, end }).pipe(response);
          return;
        }
        response.setHeader('content-length', String(size));
        createReadStream(path).pipe(response);
      });
    },
  };
}

export default defineConfig({
  base: './',
  plugins: [react(), servingSet()],
  build: {
    target: 'es2023',
    sourcemap: true,
    rollupOptions: {
      output: {
        // The map and Arrow libraries are large and change rarely, so they are split out:
        // an app-code change then invalidates a small chunk rather than the whole bundle.
        codeSplitting: {
          groups: [
            { name: 'maplibre', test: /node_modules\/maplibre-gl\// },
            { name: 'deck', test: /node_modules\/@deck\.gl\// },
            { name: 'arrow', test: /node_modules\/apache-arrow\// },
          ],
        },
      },
    },
  },
  worker: {
    format: 'es',
  },
  test: {
    // `test/` holds the contract suite, which needs a real baked artifact and so runs as a
    // separate step after the pipeline rather than on every `npm test`.
    include: ['src/**/*.test.ts'],
    environment: 'node',
  },
});
