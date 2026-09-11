/**
 * The serving manifest, validated at the boundary.
 *
 * This is the only document fetched by a fixed name; everything else it points at is
 * content-hashed and therefore immutable. Validating it with a schema rather than trusting its
 * shape is what stops a pipeline change from failing silently in the browser: a renamed field
 * would otherwise read as `undefined`, and a layer would quietly draw nothing.
 */
import { z } from 'zod';

export const FRESHNESS = ['fresh', 'late', 'stale', 'absent'] as const;

const budgetSchema = z.object({
  path_vertices: z.number().int().nonnegative(),
  path_vertex_limit: z.number().int().positive(),
  points: z.number().int().nonnegative(),
  point_limit: z.number().int().positive(),
  bytes: z.number().int().nonnegative(),
});

const layerSchema = z.object({
  id: z.string().min(1),
  kind: z.enum(['tracks', 'points']),
  url: z.string().min(1),
  format: z.literal('arrow-ipc'),
  schema_version: z.number().int(),
  min_zoom: z.number().int(),
  max_zoom: z.number().int(),
  epoch: z.string().min(1),
  observed_from: z.string().nullable().default(null),
  observed_at: z.string().nullable().default(null),
  freshness: z.enum(FRESHNESS),
  feature_count: z.number().int().nonnegative(),
  budget: budgetSchema,
});

const attributionSchema = z.object({
  source: z.string(),
  licence: z.string(),
  url: z.string(),
  text: z.string(),
});

const sourceHealthSchema = z.object({
  source: z.string(),
  state: z.string(),
  observed_at: z.string().nullable().default(null),
  detail: z.string().nullable().default(null),
});

export const manifestSchema = z.object({
  schema_version: z.number().int(),
  run_id: z.string(),
  generated_at: z.string(),
  bounds: z.tuple([z.number(), z.number(), z.number(), z.number()]),
  initial_view: z.object({
    longitude: z.number(),
    latitude: z.number(),
    zoom: z.number(),
  }),
  layers: z.array(layerSchema),
  attributions: z.array(attributionSchema),
  sources: z.array(sourceHealthSchema),
  sampling_notice: z.string(),
});

export type Manifest = z.infer<typeof manifestSchema>;
export type Layer = z.infer<typeof layerSchema>;
export type Attribution = z.infer<typeof attributionSchema>;
export type SourceHealth = z.infer<typeof sourceHealthSchema>;
export type Freshness = (typeof FRESHNESS)[number];

/**
 * The schema version this build knows how to read.
 *
 * A mismatch is reported rather than rendered. Reading a newer artifact with older code is how
 * a column that changed meaning becomes a plausible-looking wrong number on screen.
 */
export const SUPPORTED_SCHEMA_VERSION = 1;

export class ManifestVersionError extends Error {
  constructor(found: number) {
    super(
      `serving manifest is schema version ${found}, but this build reads ` +
        `version ${SUPPORTED_SCHEMA_VERSION}. Reload to pick up a newer build.`,
    );
    this.name = 'ManifestVersionError';
  }
}

export function parseManifest(payload: unknown): Manifest {
  const manifest = manifestSchema.parse(payload);
  if (manifest.schema_version !== SUPPORTED_SCHEMA_VERSION) {
    throw new ManifestVersionError(manifest.schema_version);
  }
  return manifest;
}

/** Layers that apply at a given zoom, in manifest order. */
export function layersForZoom(manifest: Manifest, zoom: number, kind: Layer['kind']): Layer[] {
  return manifest.layers.filter(
    (layer) => layer.kind === kind && zoom >= layer.min_zoom && zoom <= layer.max_zoom,
  );
}

/** The worst freshness across the layers, which is what the badge must report. */
export function overallFreshness(manifest: Manifest): Freshness {
  let worst: Freshness = 'fresh';
  for (const layer of manifest.layers) {
    if (FRESHNESS.indexOf(layer.freshness) > FRESHNESS.indexOf(worst)) {
      worst = layer.freshness;
    }
  }
  return worst;
}
