/**
 * Playback and scrubbing.
 *
 * The readout updates every frame, so it is written imperatively into a ref rather than
 * through React state (`.cursorrules` § 6): a `setState` per frame would re-render the tree
 * sixty times a second to change two text nodes.
 *
 * The label is absolute Manila time, never an offset. "14:32 PHT" is a fact a user can check
 * against; "+00:41" is an artifact of how the file happens to be encoded (invariant 6).
 */
import { useEffect, useRef, useState } from 'react';

import { formatManilaTime } from '../clock';
import { useAppStore } from '../store';
import { animationClock } from './MapView';

export function TimeScrubber({ epoch }: { epoch: Date }): React.JSX.Element {
  const readout = useRef<HTMLSpanElement>(null);
  const slider = useRef<HTMLInputElement>(null);
  const [range, setRange] = useState<[number, number]>([0, 0]);

  const animated = useAppStore((state) => state.animated);
  const playing = useAppStore((state) => state.playing);
  const setPlaying = useAppStore((state) => state.setPlaying);

  useEffect(() => {
    return animationClock.subscribe((seconds) => {
      const instant = new Date(epoch.getTime() + seconds * 1000);
      if (readout.current !== null) {
        readout.current.textContent = formatManilaTime(instant);
      }
      // Writing `value` rather than re-rendering keeps the slider in step with the clock
      // without React seeing a change every frame. Skipped while dragging so the thumb is
      // not fought for by the animation.
      if (slider.current !== null && document.activeElement !== slider.current) {
        slider.current.value = String(seconds);
      }
    });
  }, [epoch]);

  // The span is only known once the artifacts have decoded, and the clock learns it first, so
  // the bounds are read back from the clock rather than plumbed through the component tree.
  useEffect(() => {
    return animationClock.subscribeRange((start, end) => setRange([start, end]));
  }, []);

  const span = range[1] - range[0];
  if (span <= 0) {
    return (
      <section className="panel" aria-label="Playback">
        <p className="muted">
          Nothing to play back — this build observed no movement in its window.
        </p>
      </section>
    );
  }

  // Only state changes here. `MapView` owns the clock, so the button, a lost graphics
  // context and the capability probe all reach the clock by the same route.
  const toggle = (): void => setPlaying(!playing);

  return (
    <section className="panel scrubber" aria-label="Playback">
      <div className="scrubber-head">
        <button
          type="button"
          onClick={toggle}
          disabled={!animated}
          title={animated ? undefined : 'Animation is unavailable on this device.'}
        >
          {playing ? 'Pause' : 'Play'}
        </button>
        <span className="readout" ref={readout} aria-live="off" />
      </div>

      <input
        ref={slider}
        type="range"
        min={range[0]}
        max={range[1]}
        step={Math.max(1, Math.round(span / 600))}
        defaultValue={range[0]}
        aria-label="Observation time"
        onChange={(event) => {
          setPlaying(false);
          animationClock.setPosition(Number(event.target.value));
        }}
      />

      <p className="muted small">
        {formatManilaTime(new Date(epoch.getTime() + range[0] * 1000))} to{' '}
        {formatManilaTime(new Date(epoch.getTime() + range[1] * 1000))}
      </p>
    </section>
  );
}
