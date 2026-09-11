/**
 * UI state.
 *
 * Deliberately small. The animation position is *not* here: it changes every frame and lives
 * in the animation clock, which publishes to subscribers rather than through React
 * (`.cursorrules` § 6). What is here is what a render actually depends on.
 */
import { create } from 'zustand';

import type { Capability } from './capability';
import type { Manifest } from './manifest';

export interface HoverTarget {
  entityId: string;
  label: string;
  mode: 'air' | 'sea';
  x: number;
  y: number;
}

interface AppState {
  manifest: Manifest | null;
  capability: Capability | null;
  /** Set when the probe or the runtime says the animation must not run. */
  animated: boolean;
  playing: boolean;
  zoom: number;
  showAir: boolean;
  showSea: boolean;
  hover: HoverTarget | null;
  /** Surfaced in the UI. A silent failure is worse than a visible one. */
  error: string | null;

  setManifest: (manifest: Manifest) => void;
  setCapability: (capability: Capability) => void;
  setPlaying: (playing: boolean) => void;
  setZoom: (zoom: number) => void;
  toggleAir: () => void;
  toggleSea: () => void;
  setHover: (hover: HoverTarget | null) => void;
  setError: (error: string | null) => void;
  /** Called on WebGL context loss, which must rebuild rather than white-screen. */
  disableAnimation: (reason: string) => void;
}

export const useAppStore = create<AppState>()((set) => ({
  manifest: null,
  capability: null,
  animated: false,
  playing: false,
  zoom: 0,
  showAir: true,
  showSea: true,
  hover: null,
  error: null,

  setManifest: (manifest) => set({ manifest }),
  // Reduced motion does not disable the animation — it declines to start it. Scrubbing is
  // still the primary way to read the data, and taking it away would be a worse answer.
  setCapability: (capability) =>
    set({
      capability,
      animated: capability.animated,
      playing: capability.animated && !capability.reducedMotion,
    }),
  setPlaying: (playing) => set({ playing }),
  setZoom: (zoom) => set({ zoom }),
  toggleAir: () => set((state) => ({ showAir: !state.showAir })),
  toggleSea: () => set((state) => ({ showSea: !state.showSea })),
  setHover: (hover) => set({ hover }),
  setError: (error) => set({ error }),
  disableAnimation: (reason) => set({ animated: false, playing: false, error: reason }),
}));
