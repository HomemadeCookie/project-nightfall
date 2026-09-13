import { defineConfig } from 'vitest/config';

/**
 * The contract suite runs against a real serving set, so it is deliberately separate from
 * `npm test`: it is a step that follows the pipeline, not a unit test.
 */
export default defineConfig({
  test: {
    include: ['test/**/*.test.ts'],
    environment: 'node',
  },
});
