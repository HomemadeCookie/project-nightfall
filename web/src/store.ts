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
  /**
   * Everything the app has had to tell the user, in the order it arose. A silent failure is
   * worse than a visible one — and a list rather than one slot because these accumulate
   * independently: a device without acceleration and an unpublished basemap are two separate
   * facts, and holding one would have quietly dropped the other.
   */
  notices: readonly string[];

  setManifest: (manifest: Manifest) => void;
  setCapability: (capability: Capability) => void;
  setPlaying: (playing: boolean) => void;
  setZoom: (zoom: number) => void;
  toggleAir: () => void;
  toggleSea: () => void;
  setHover: (hover: HoverTarget | null) => void;
  notify: (notice: string) => void;
  dismiss: (notice: string) => void;
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
  notices: [],

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
  // Repeats are dropped. An effect that runs twice, which is what React's strict mode does on
  // purpose, should not produce the same sentence twice.
  notify: (notice) =>
    set((state) =>
      state.notices.includes(notice) ? state : { notices: [...state.notices, notice] },
    ),
  dismiss: (notice) =>
    set((state) => ({ notices: state.notices.filter((entry) => entry !== notice) })),
  disableAnimation: (reason) =>
    set((state) => ({
      animated: false,
      playing: false,
      notices: state.notices.includes(reason) ? state.notices : [...state.notices, reason],
    })),
}));
