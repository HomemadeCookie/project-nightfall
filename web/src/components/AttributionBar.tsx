/**
 * Attribution and the sampling notice.
 *
 * Not a footer. Every credit here is generated from the licence registry the collectors are
 * bound by (`.cursorrules` § 3), so a source added to the pipeline appears on screen without
 * anyone remembering to add it, and a source whose licence requires attribution cannot be
 * shipped without it.
 *
 * The sampling notice sits next to the credits because it carries the same weight: the
 * overlay shows short observed windows, and a viewer who reads an empty sea as a quiet sea
 * has been misled by the picture (invariant 7).
 */
import { useState } from 'react';

import type { Manifest } from '../manifest';

export function AttributionBar({ manifest }: { manifest: Manifest }): React.JSX.Element {
  const [open, setOpen] = useState(false);

  return (
    <div className="attribution">
      <button type="button" className="link" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? 'Hide sources' : 'Sources and limits'}
      </button>

      {open ? (
        <div className="attribution-detail">
          <p className="notice">{manifest.sampling_notice}</p>
          <ul>
            {manifest.attributions.map((credit) => (
              <li key={credit.source}>
                <a href={credit.url} target="_blank" rel="noreferrer noopener">
                  {credit.text}
                </a>
                <span className="muted"> · {credit.licence}</span>
              </li>
            ))}
          </ul>
          <p className="muted small">
            Basemap © OpenStreetMap contributors, built with Protomaps. Rendered from tiles
            published alongside this app.
          </p>
        </div>
      ) : (
        <span className="attribution-sources muted small">
          {manifest.attributions.map((credit) => credit.source).join(' · ')}
        </span>
      )}
    </div>
  );
}
