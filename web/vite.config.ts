import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

/**
 * The app is a static bundle with no server (README § Infrastructure). `base` is relative so
 * the same build works at a GitHub Pages project path and at the root of any other free
 * static host, which is the escape hatch the manifest-of-relative-URLs design exists for.
 *
 * In development the serving set is read straight from the pipeline's output directory rather
 * than copied into the repository, because data files never enter git history
 * (`.cursorrules` § 4).
 */
export default defineConfig({
  base: './',
  plugins: [react()],
  publicDir: 'public',
  server: {
    fs: { allow: ['..'] },
  },
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
