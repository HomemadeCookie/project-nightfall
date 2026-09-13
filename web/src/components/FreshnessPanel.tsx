/**
 * Freshness and provenance.
 *
 * Invariant 3 means a failed collection leaves the previous artifacts serving. That is only
 * acceptable if the interface says so, so this panel is not decoration: it is the mechanism
 * that keeps stale data from passing as current, and it surfaces a stalled pipeline within one
 * cycle (README § Risks, upstream availability).
 */
import { formatAge, formatManila } from '../clock';
import type { Freshness, Manifest } from '../manifest';
import { overallFreshness } from '../manifest';

const WORDING: Record<Freshness, string> = {
  fresh: 'Current',
  late: 'Behind schedule',
  stale: 'Stale — the pipeline has stopped updating',
  absent: 'No observations in this window',
};

export function FreshnessPanel({ manifest }: { manifest: Manifest }): React.JSX.Element {
  const state = overallFreshness(manifest);
  const observed = manifest.layers
    .map((layer) => layer.observed_at)
    .filter((value): value is string => value !== null)
    .sort()
    .at(-1);

  const totalVertices = manifest.layers.reduce((sum, layer) => sum + layer.budget.path_vertices, 0);
  const vertexLimit = manifest.layers[0]?.budget.path_vertex_limit ?? 0;

  return (
    <section className="panel" aria-label="Data freshness">
      <h2>
        <span className={`dot dot-${state}`} aria-hidden="true" />
        {WORDING[state]}
      </h2>

      {observed === undefined ? (
        <p className="muted">Nothing was observed in the window this build covers.</p>
      ) : (
        <p>
          Latest observation {formatManila(new Date(observed))}
          <span className="muted"> · {formatAge(new Date(observed))}</span>
        </p>
      )}

      <dl>
        {manifest.sources.map((source) => (
          <div key={source.source} className="row">
            <dt>{source.source}</dt>
            <dd className={source.state === 'ok' ? '' : 'warn'}>
              {source.state === 'not_configured' ? 'not configured' : source.state}
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
