/**
 * The map.
 *
 * The animation deliberately does not flow through React. The clock publishes a position, and
 * this component pushes it into deck.gl by rebuilding layer objects with a new `currentTime`
 * prop — cheap, because the layers' `data` is the same transferred buffers every frame, so
 * deck.gl reuses the GPU buffers and only the uniform changes. Re-rendering React at 60 Hz
 * would cost more than the frame it was trying to draw.
 */

import type { Layer as DeckLayer, PickingInfo } from '@deck.gl/core';
import { MapLibreOverlay } from '@deck.gl/maplibre';
// maplibre-gl 6 publishes named exports only; there is no namespace default to reach through.
import {
  addProtocol,
  Map as MapLibreMap,
  NavigationControl,
  removeProtocol,
  setWorkerUrl,
} from 'maplibre-gl';
// Bundled here rather than left to MapLibre to find. It derives its worker's URL at runtime,
// from `import.meta.url`, assuming the file sits next to the module that asked for it — which
// is true of the published package and false of every bundle, so the request lands on a
// hashed asset path that does not exist and the host answers with HTML. The tiles are then
// fetched and never parsed: a blank basemap, and no error except a MIME complaint about a
// script nobody wrote. Asking the bundler for the URL makes it a build-time fact.
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { Protocol } from 'pmtiles';
import { useEffect, useRef } from 'react';

import { basemapAvailable, basemapStyle, blankStyle } from '../basemap';
import { AnimationClock } from '../clock';
import {
  BASEMAP_URL,
  MIN_TRACK_ZOOM,
  PLAYBACK_RATE,
  playbackRateForSpan,
  servingUrl,
} from '../config';
import {
  filterRange,
  pointColours,
  pointFilters,
  pointLayer,
  pointModes,
  timeFilterRange,
  trackLayer,
  vertexColours,
  vertexFilters,
  vertexModes,
} from '../layers/mobility';
import { layersForZoom, type Manifest } from '../manifest';
import { type HoverTarget, useAppStore } from '../store';
import type { PointsBundle, TracksBundle } from '../workers/bundles';
import { MODE_SEA, readString } from '../workers/bundles';
import { loadPoints, loadTracks } from '../workers/client';

import 'maplibre-gl/dist/maplibre-gl.css';

setWorkerUrl(maplibreWorkerUrl);

export const animationClock = new AnimationClock(PLAYBACK_RATE);

/** Decoded artifacts plus the GPU attributes derived from them, built once per load. */
interface Loaded {
  tracks: Map<string, { bundle: TracksBundle; colours: Uint8Array; filters: Float32Array }>;
  points: { bundle: PointsBundle; colours: Uint8Array; filters: Float32Array } | null;
}

export function MapView({ manifest }: { manifest: Manifest }): React.JSX.Element {
  const container = useRef<HTMLDivElement>(null);
  const loaded = useRef<Loaded>({ tracks: new Map(), points: null });
  const overlayRef = useRef<MapLibreOverlay | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const zoomRef = useRef(manifest.initial_view.zoom);

  const setZoom = useAppStore((state) => state.setZoom);
  const setHover = useAppStore((state) => state.setHover);
  const notify = useAppStore((state) => state.notify);
  const disableAnimation = useAppStore((state) => state.disableAnimation);
  const setAvailableSpan = useAppStore((state) => state.setAvailableSpan);

  // One effect owns the map's whole lifetime. Splitting it across effects is how a map ends
  // up initialised twice under StrictMode.
  useEffect(() => {
    const element = container.current;
    if (element === null) return;

    const protocol = new Protocol();
    addProtocol('pmtiles', protocol.tile);

    let disposed = false;
    let created: MapLibreMap | null = null;
    let overlay: MapLibreOverlay | null = null;
    let unsubscribe: (() => void) | null = null;

    const rebuild = (): void => {
      if (disposed || overlay === null) return;
      const { showAir, showSea, playing } = useAppStore.getState();
      overlay.setProps({
        layers: buildLayers(loaded.current, zoomRef.current, {
          manifest,
          showAir,
          showSea,
          playing,
        }),
      });
    };

    void (async () => {
      const hasBasemap = await basemapAvailable(BASEMAP_URL);
      if (disposed) return;

      const map = new MapLibreMap({
        container: element,
        style: hasBasemap ? basemapStyle(BASEMAP_URL) : blankStyle(),
        center: [manifest.initial_view.longitude, manifest.initial_view.latitude],
        zoom: manifest.initial_view.zoom,
        maxBounds: [
          [manifest.bounds[0] - 2, manifest.bounds[1] - 2],
          [manifest.bounds[2] + 2, manifest.bounds[3] + 2],
        ],
        attributionControl: false,
        canvasContextAttributes: {
          contextType: 'webgl2',
          // A software rasteriser reports a working context and then runs at a few frames a
          // second. The map still draws; the capability probe is what withholds the
          // animation, so refusing the context here would lose the static view as well.
          failIfMajorPerformanceCaveat: false,
          powerPreference: 'high-performance',
        },
      });
      created = map;
      mapRef.current = map;
      // Publish the opening zoom immediately. Waiting for the first `zoomend` would leave the
      // UI describing a zoom level the user is not looking at.
      setZoom(manifest.initial_view.zoom);

      if (!hasBasemap) {
        notify(
          'Basemap tiles are not published yet, so the map is showing positions without ' +
            'geographic context.',
        );
      }

      // A lost context must rebuild rather than white-screen (README § Risks).
      map.getCanvas().addEventListener('webglcontextlost', (event) => {
        event.preventDefault();
        disableAnimation('Graphics context was lost. The map has switched to a static view.');
      });

      overlay = new MapLibreOverlay({
        interleaved: false,
        layers: [],
        // Tracks are drawn barely two pixels wide. Exact-pixel picking would make hover a
        // test of mouse precision rather than a way to read the map, so the pick is allowed a
        // radius of roughly a fingertip — still tighter than the spacing between tracks, and
        // the nearest match wins where they do converge.
        pickingRadius: 10,
        // deck.gl's own tooltip is bypassed: it takes a plain string, and the detail here is
        // two lines of structured text plus a mode swatch.
        onHover: (info: PickingInfo) => {
          setHover(describe(loaded.current, info));
        },
      });
      overlayRef.current = overlay;
      map.addControl(overlay);
      map.addControl(new NavigationControl({ showCompass: false }), 'top-right');

      map.on('zoomend', () => {
        const zoom = map.getZoom();
        zoomRef.current = zoom;
        setZoom(zoom);
        rebuild();
      });

      unsubscribe = animationClock.subscribe(rebuild);

      // A layer that fails to load is reported, not fatal. The layers are independent, and
      // blanking the map because one of several artifacts is missing would throw away the
      // data that did arrive (README § Risks, degrade rather than fail).
      const failures = await loadArtifacts(manifest, loaded.current);
      if (disposed) return;
      for (const failure of failures) {
        notify(failure);
      }

      const [start, end] = spanOf(loaded.current);
      setAvailableSpan(start, end);
      animationClock.setRate(playbackRateForSpan(end - start));
      animationClock.setRange(start, end);
      // A clock that is not about to run is parked at the end of the window rather than at
      // its first instant, so the opening view is everything that was observed instead of a
      // blank map — the same reason the default zoom sits at the track gate.
      const { animated: willAnimate, playing: willPlay } = useAppStore.getState();
      if (!(willAnimate && willPlay)) {
        animationClock.setPosition(end);
      }
      rebuild();
    })();

    return () => {
      disposed = true;
      unsubscribe?.();
      animationClock.pause();
      overlay?.finalize();
      created?.remove();
      removeProtocol('pmtiles');
      overlayRef.current = null;
      mapRef.current = null;
    };
  }, [manifest, setZoom, notify, setHover, disableAnimation, setAvailableSpan]);

  // Layer visibility is React state, so it rebuilds through the same path as a zoom change.
  const showAir = useAppStore((state) => state.showAir);
  const showSea = useAppStore((state) => state.showSea);
  const animated = useAppStore((state) => state.animated);
  const playing = useAppStore((state) => state.playing);
  useEffect(() => {
    overlayRef.current?.setProps({
      layers: buildLayers(loaded.current, zoomRef.current, {
        manifest,
        showAir,
        showSea,
        playing,
      }),
    });
  }, [manifest, showAir, showSea, playing]);

  // The clock is driven from state so that whatever changes `playing` — the scrubber, a lost
  // context, the capability probe — gets the same behaviour. Playing a clock with no range
  // yet is a no-op, and `setRange` publishes once the artifacts land.
  useEffect(() => {
    if (playing && animated) {
      animationClock.play();
    } else {
      animationClock.pause();
    }
  }, [playing, animated]);

  useEffect(() => {
    const clear = (): void => setHover(null);
    window.addEventListener('blur', clear);
    return () => window.removeEventListener('blur', clear);
  }, [setHover]);

  return <div ref={container} className="map" />;
}

/** Loads every layer, returning a sentence per layer that could not be loaded. */
async function loadArtifacts(manifest: Manifest, into: Loaded): Promise<string[]> {
  const outcomes = await Promise.allSettled(
    manifest.layers.map(async (layer) => {
      if (layer.kind === 'tracks') {
        const bundle = await loadTracks(servingUrl(layer.url));
        const modes = vertexModes(bundle);
        into.tracks.set(layer.id, {
          bundle,
          colours: vertexColours(bundle),
          filters: vertexFilters(modes, bundle.timestamps),
        });
      } else {
        const bundle = await loadPoints(servingUrl(layer.url));
        const modes = pointModes(bundle);
        into.points = {
          bundle,
          colours: pointColours(bundle),
          filters: pointFilters(modes, bundle.timestamps),
        };
      }
    }),
  );

  return outcomes.flatMap((outcome, index) => {
    if (outcome.status === 'fulfilled') return [];
    const id = manifest.layers[index]?.id ?? 'unknown';
    const reason: unknown = outcome.reason;
    const detail = reason instanceof Error ? reason.message : String(reason);
    return [`Layer ${id} could not be loaded: ${detail}`];
  });
}

function spanOf(loaded: Loaded): [number, number] {
  let start = Number.POSITIVE_INFINITY;
  let end = Number.NEGATIVE_INFINITY;
  for (const { bundle } of loaded.tracks.values()) {
    if (bundle.length === 0) continue;
    start = Math.min(start, bundle.timeRange[0]);
    end = Math.max(end, bundle.timeRange[1]);
  }
  if (loaded.points !== null && loaded.points.bundle.length > 0) {
    start = Math.min(start, loaded.points.bundle.timeRange[0]);
    end = Math.max(end, loaded.points.bundle.timeRange[1]);
  }
  return Number.isFinite(start) && Number.isFinite(end) ? [start, end] : [0, 0];
}

interface RenderInputs {
  manifest: Manifest;
  showAir: boolean;
  showSea: boolean;
  playing: boolean;
}

function buildLayers(loaded: Loaded, zoom: number, inputs: RenderInputs): DeckLayer[] {
  const { manifest, showAir, showSea, playing } = inputs;
  const layers: DeckLayer[] = [];
  const currentTime = animationClock.currentPosition;
  const [spanStart] = animationClock.range;
  const range = timeFilterRange(filterRange(showAir, showSea), spanStart, currentTime);

  // Zoom-gated level of detail: individual tracks only from zoom 9 (`.cursorrules` § 6).
  if (zoom >= MIN_TRACK_ZOOM) {
    for (const descriptor of layersForZoom(manifest, zoom, 'tracks')) {
      const entry = loaded.tracks.get(descriptor.id);
      if (entry === undefined) continue;
      layers.push(
        trackLayer({
          id: descriptor.id,
          bundle: entry.bundle,
          colours: entry.colours,
          filters: entry.filters,
          range,
          currentTime,
          playing,
        }),
      );
    }
  }

  if (loaded.points !== null) {
    layers.push(
      pointLayer({
        id: 'mobility-points',
        bundle: loaded.points.bundle,
        colours: loaded.points.colours,
        filters: loaded.points.filters,
        range,
      }),
    );
  }
  return layers;
}

/**
 * Resolve a pick into hover detail.
 *
 * Strings are read out of the Arrow buffers here, on hover, rather than being materialised as
 * JavaScript strings at load time — the reason the bundles carry a string column at all.
 */
function describe(loaded: Loaded, info: PickingInfo): HoverTarget | null {
  const layerId = info.layer?.id;
  if (layerId === undefined || info.index < 0) return null;
  const entry = loaded.tracks.get(layerId);
  const bundle = entry?.bundle ?? (layerId === 'mobility-points' ? loaded.points?.bundle : null);
  if (bundle === null || bundle === undefined) return null;

  const label = readString(bundle.labels, info.index);
  const entityId = readString(bundle.entityIds, info.index);
  const mode = bundle.modes[info.index] === MODE_SEA ? 'sea' : 'air';
  return {
    entityId: entityId === '' ? 'identity not reported' : entityId,
    label: label === '' ? entityId : label,
    mode,
    x: info.x,
    y: info.y,
  };
}
