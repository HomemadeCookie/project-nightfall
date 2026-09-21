/**
 * Freshness and provenance.
 *
 * Invariant 3 means a failed collection leaves the previous artifacts serving. That is only
 * acceptable if the interface says so, so this panel is not decoration: it is the mechanism
 * that keeps stale data from passing as current, and it surfaces a stalled pipeline within one
 * cycle (README § Risks, upstream availability).
 *
 * Fixture and archive builds must not read as a live feed. A three-minute sample must not
 * read as a multi-year history.
 */
import { formatAge, formatManila, formatObservedSpan } from '../clock';
import type { Freshness, Manifest, ObservationKind } from '../manifest';
import { overallFreshness } from '../manifest';

const FRESHNESS_WORDING: Record<Freshness, string> = {
  fresh: 'Current',
  late: 'Behind schedule',
  stale: 'Stale — the pipeline has stopped updating',
  absent: 'No observations in this window',
  archive: 'Historical archive',
  fixture: 'Demo fixture',
};

const KIND_WORDING: Record<ObservationKind, string | null> = {
  live: null,
  archive: 'Historical archive',
  fixture: 'Demo fixture',
  mixed: 'Historical archive + fixture',
};

const SOURCE_STATE: Record<string, string> = {
  ok: 'live',
  outage: 'outage',
  not_configured: 'not configured',
  fixture: 'fixture',
  archive: 'archive',
};

function heading(manifest: Manifest): string {
  return KIND_WORDING[manifest.observation_kind] ?? FRESHNESS_WORDING[overallFreshness(manifest)];
}

function headingClass(manifest: Manifest): Freshness {
  if (manifest.observation_kind === 'fixture') return 'fixture';
  if (manifest.observation_kind === 'archive' || manifest.observation_kind === 'mixed') {
    return 'archive';
  }
  return overallFreshness(manifest);
}

function formatCount(value: number): string {
  return value.toLocaleString('en-GB');
}

export function FreshnessPanel({ manifest }: { manifest: Manifest }): React.JSX.Element {
  const state = headingClass(manifest);
  const from = manifest.available_from ?? manifest.layers[0]?.observed_from;
  const until = manifest.available_until ?? manifest.layers[0]?.observed_at;
  const totalVertices = manifest.layers.reduce((sum, layer) => sum + layer.budget.path_vertices, 0);
  const vertexLimit = manifest.layers[0]?.budget.path_vertex_limit ?? 0;

  return (
    <section className="panel" aria-label="Data freshness">
      <h2>
        <span className={`dot dot-${state}`} aria-hidden="true" />
        {heading(manifest)}
      </h2>

      {from === null || until === null || from === undefined || until === undefined ? (
        <p className="muted">Nothing was observed in the window this build covers.</p>
      ) : (
        <p>
          {formatObservedSpan(new Date(from), new Date(until))}
          {manifest.observation_kind === 'live' ? (
            <span className="muted"> · {formatAge(new Date(until))}</span>
          ) : null}
        </p>
      )}

      <dl>
        <div className="row">
          <dt>Aircraft</dt>
          <dd>
            {formatCount(manifest.census.air.unique_entities)} unique ·{' '}
            {formatCount(manifest.census.air.position_fixes)} fixes
          </dd>
        </div>
        <div className="row">
          <dt />
          <dd className="muted">
            {formatCount(manifest.census.air.track_segments)} tracks ·{' '}
            {formatCount(manifest.census.air.isolated_points)} isolated
          </dd>
        </div>
        <div className="row">
          <dt>Vessels</dt>
          <dd>
            {formatCount(manifest.census.sea.unique_entities)} unique ·{' '}
            {formatCount(manifest.census.sea.position_fixes)} fixes
          </dd>
        </div>
        <div className="row">
          <dt />
          <dd className="muted">
            {formatCount(manifest.census.sea.track_segments)} tracks ·{' '}
            {formatCount(manifest.census.sea.isolated_points)} isolated
          </dd>
        </div>
        {manifest.sources.map((source) => (
          <div key={source.source} className="row">
            <dt>{source.source}</dt>
            <dd className={source.state === 'ok' ? '' : 'warn'}>
              {SOURCE_STATE[source.state] ?? source.state}
              {source.detail === null ? null : <span className="muted"> — {source.detail}</span>}
            </dd>
          </div>
        ))}
      </dl>

      <p className="muted small">
        {/* Invariant 7: every rendered figure resolves to the run that produced it. */}
        Build {manifest.run_id} · generated {formatManila(new Date(manifest.generated_at))} ·{' '}
        {totalVertices.toLocaleString()} of {vertexLimit.toLocaleString()} vertex budget
      </p>
    </section>
  );
}
