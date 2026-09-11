/**
 * Application shell.
 *
 * The manifest is fetched once and validated before anything renders, because every artifact
 * URL, zoom band and epoch comes from it. Rendering a map first and discovering later that the
 * manifest is a version this build cannot read would put unexplained geometry on screen.
 */
import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';

import { probeCapability } from './capability';
import { AttributionBar } from './components/AttributionBar';
import { FreshnessPanel } from './components/FreshnessPanel';
import { MapView } from './components/MapView';
import { TimeScrubber } from './components/TimeScrubber';
import { MANIFEST_URL } from './config';
import { type Manifest, ManifestVersionError, parseManifest } from './manifest';
import { useAppStore } from './store';

async function fetchManifest(): Promise<Manifest> {
  // `no-store` is deliberate: the manifest is the one document fetched by a fixed name, so a
  // cached copy would pin the app to artifacts that have already been replaced.
  const response = await fetch(MANIFEST_URL, { cache: 'no-store' });
  if (!response.ok) {
    throw new Error(
      `The serving manifest could not be loaded (HTTP ${response.status}). ` +
        'The pipeline may not have published a build yet.',
    );
  }
  return parseManifest(await response.json());
}

export function App(): React.JSX.Element {
  const setManifest = useAppStore((state) => state.setManifest);
  const setCapability = useAppStore((state) => state.setCapability);
  const capability = useAppStore((state) => state.capability);
  const error = useAppStore((state) => state.error);
  const setError = useAppStore((state) => state.setError);

  useEffect(() => {
    const probe = probeCapability();
    setCapability(probe);
    if (probe.reason !== null) setError(probe.reason);
  }, [setCapability, setError]);

  const manifestQuery = useQuery({
    queryKey: ['manifest'],
    queryFn: fetchManifest,
    // A version mismatch will not resolve by asking again.
    retry: (attempts, cause) => !(cause instanceof ManifestVersionError) && attempts < 2,
  });

  const manifest = manifestQuery.data;
  useEffect(() => {
    if (manifest !== undefined) setManifest(manifest);
  }, [manifest, setManifest]);

  if (manifestQuery.isPending) {
    return <Splash message="Loading the latest build…" />;
  }
  if (manifestQuery.isError) {
    return <Splash message={describeError(manifestQuery.error)} tone="error" />;
  }
  if (manifest === undefined) {
    return <Splash message="No build is available." tone="error" />;
  }
  if (capability !== null && !capability.webgl2) {
    return (
      <Splash message={capability.reason ?? 'This browser cannot render the map.'} tone="error" />
    );
  }

  const epoch = new Date(manifest.layers[0]?.epoch ?? manifest.generated_at);

  return (
    <div className="app">
      <MapView manifest={manifest} />

      <header className="header">
        <h1>project&#8239;nightfall</h1>
        <p className="muted small">Observed movement over the Philippines</p>
      </header>

      <aside className="sidebar">
        <FreshnessPanel manifest={manifest} />
        <LayerToggles />
        <TimeScrubber epoch={epoch} />
      </aside>

      {error === null ? null : (
        <div className="banner" role="status">
          <span>{error}</span>
          <button type="button" className="link" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      <AttributionBar manifest={manifest} />
      <HoverCard />
    </div>
  );
}

function LayerToggles(): React.JSX.Element {
  const showAir = useAppStore((state) => state.showAir);
  const showSea = useAppStore((state) => state.showSea);
  const toggleAir = useAppStore((state) => state.toggleAir);
  const toggleSea = useAppStore((state) => state.toggleSea);
  const zoom = useAppStore((state) => state.zoom);

  return (
    <section className="panel" aria-label="Layers">
      <label>
        <input type="checkbox" checked={showAir} onChange={toggleAir} />
        <span className="swatch swatch-air" aria-hidden="true" />
        Aircraft
      </label>
      <label>
        <input type="checkbox" checked={showSea} onChange={toggleSea} />
        <span className="swatch swatch-sea" aria-hidden="true" />
        Vessels
      </label>
      <p className="muted small">Zoom {zoom.toFixed(1)}</p>
    </section>
  );
}

/** Hover detail. deck.gl's own tooltip is bypassed so the markup stays in the app's voice. */
function HoverCard(): React.JSX.Element | null {
  const hover = useAppStore((state) => state.hover);
  if (hover === null) return null;
  return (
    <div className="hovercard" style={{ left: hover.x, top: hover.y }}>
      <strong>{hover.label}</strong>
      <span className="muted small">{hover.entityId}</span>
    </div>
  );
}

function describeError(cause: unknown): string {
  if (cause instanceof ManifestVersionError) return cause.message;
  if (cause instanceof Error) return cause.message;
  return 'The latest build could not be loaded.';
}

function Splash({
  message,
  tone = 'info',
}: {
  message: string;
  tone?: 'info' | 'error';
}): React.JSX.Element {
  return (
    <div className={`splash splash-${tone}`}>
      <h1>project&#8239;nightfall</h1>
      <p>{message}</p>
    </div>
  );
}
