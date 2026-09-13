/**
 * Device capability probe.
 *
 * The single largest product risk is the map crashing the browser (README § Risks), so the
 * app decides what it can afford before it draws anything rather than after the tab dies. A
 * device that fails the probe still gets the data — as a static picture of the observed span
 * — because a readable still is worth more than an animation that stutters or crashes.
 */

export interface Capability {
  /** WebGL2 is required. The WebGPU backend is excluded: it cannot pick, and hover is core. */
  webgl2: boolean;
  /** A software rasteriser can draw the map, but not animate it at an acceptable frame rate. */
  softwareRenderer: boolean;
  /** `navigator.deviceMemory` in GB where the browser reports it. */
  memoryGb: number | null;
  /** The user has asked the platform for reduced motion, which the playhead must respect. */
  reducedMotion: boolean;
  /** Whether the animation loop should run at all. */
  animated: boolean;
  reason: string | null;
}

const SOFTWARE_RENDERERS = ['swiftshader', 'llvmpipe', 'software', 'basic render'];

/** Below this the animation is likely to be the thing that exhausts the tab. */
const MIN_MEMORY_GB = 2;

export function probeCapability(): Capability {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const canvas = document.createElement('canvas');
  const gl = canvas.getContext('webgl2');
  if (gl === null) {
    return {
      webgl2: false,
      softwareRenderer: false,
      memoryGb: readMemoryGb(),
      reducedMotion,
      animated: false,
      reason: 'This browser does not support WebGL2, which the map requires.',
    };
  }

  const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
  const renderer =
    debugInfo === null
      ? ''
      : String(gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) ?? '').toLowerCase();
  const softwareRenderer = SOFTWARE_RENDERERS.some((name) => renderer.includes(name));
  const memoryGb = readMemoryGb();
  const lowMemory = memoryGb !== null && memoryGb < MIN_MEMORY_GB;

  // Releasing the probe context matters: browsers cap simultaneous WebGL contexts, and a
  // leaked one can cost the map the context it needs.
  gl.getExtension('WEBGL_lose_context')?.loseContext();

  let reason: string | null = null;
  if (softwareRenderer) {
    reason = 'No hardware graphics acceleration detected — showing a static view.';
  } else if (lowMemory) {
    reason = 'Limited device memory — showing a static view.';
  } else if (reducedMotion) {
    reason = 'Reduced motion is enabled, so playback starts paused. Scrubbing still works.';
  }

  return {
    webgl2: true,
    softwareRenderer,
    memoryGb,
    reducedMotion,
    animated: !softwareRenderer && !lowMemory,
    reason,
  };
}

function readMemoryGb(): number | null {
  const value = (navigator as Navigator & { deviceMemory?: number }).deviceMemory;
  return typeof value === 'number' ? value : null;
}
