/**
 * Where the serving set lives.
 *
 * A single relative base, because the browser must never call a third party (invariant 1) and
 * because relocating to another free static host has to be a URL change rather than a rebuild
 * (README § Risks, platform rule changes). Override with `VITE_SERVING_BASE` for a deployment
 * that separates the app from its data.
 */
const RAW_BASE: string = import.meta.env.VITE_SERVING_BASE ?? 'serving';

export const SERVING_BASE = RAW_BASE.replace(/\/+$/, '');

export function servingUrl(name: string): string {
  return `${SERVING_BASE}/${name}`;
}

export const MANIFEST_URL = servingUrl('manifest.json');

/**
 * Self-hosted basemap tiles. Built by a scheduled job from a Protomaps build and published
 * alongside the app, because a hosted tile service is a metered billing relationship
 * (`.cursorrules` § 1) and MapLibre's demo styles are not a licence to rely on.
 */
export const BASEMAP_URL = servingUrl('basemap.pmtiles');

/** Individual tracks are only drawn from this zoom up (`.cursorrules` § 6). */
export const MIN_TRACK_ZOOM = 9;

/** How long a trail persists behind the animation head, in artifact seconds. */
export const TRAIL_LENGTH_S = 240;

/** Artifact seconds advanced per wall-clock second while playing a short window. */
export const PLAYBACK_RATE = 20;

/** A day-long window at `PLAYBACK_RATE` would take over an hour to play; scale so a pass is ~45s. */
export const PLAYBACK_TARGET_S = 45;

export function playbackRateForSpan(spanS: number): number {
  if (spanS <= 0) return PLAYBACK_RATE;
  return Math.max(PLAYBACK_RATE, spanS / PLAYBACK_TARGET_S);
}
