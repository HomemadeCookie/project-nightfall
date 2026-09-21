/**
 * Observed-range picker.
 *
 * The control is clamped to the baked min/max. There is no year that can be typed that we
 * did not observe — a full Year A–B archive does not exist at $0.00, and a slider that
 * could be dragged into that fiction would be a lie.
 */
import { useEffect, useState } from 'react';
import {
  formatObservedSpan,
  fromManilaWallTime,
  manilaDateInput,
  manilaTimeInput,
  toManilaWallTime,
} from '../clock';
import { playbackRateForSpan } from '../config';
import { useAppStore } from '../store';
import { animationClock } from './MapView';

export function RangeControl({ epoch }: { epoch: Date }): React.JSX.Element {
  const availableStart = useAppStore((state) => state.availableStart);
  const availableEnd = useAppStore((state) => state.availableEnd);
  const playing = useAppStore((state) => state.playing);
  const setPlaying = useAppStore((state) => state.setPlaying);
  const [selected, setSelected] = useState<[number, number]>([availableStart, availableEnd]);

  useEffect(() => {
    return animationClock.subscribeRange((start, end) => setSelected([start, end]));
  }, []);

  const span = availableEnd - availableStart;
  if (span <= 0) {
    return (
      <section className="panel" aria-label="Observation range">
        <p className="muted">No observed span — the range control has nothing to clamp to.</p>
      </section>
    );
  }

  const availFrom = new Date(epoch.getTime() + availableStart * 1000);
  const availTo = new Date(epoch.getTime() + availableEnd * 1000);
  const sameDay = manilaDateInput(availFrom) === manilaDateInput(availTo);

  const apply = (startS: number, endS: number): void => {
    const lo = Math.max(availableStart, Math.min(startS, endS));
    const hi = Math.min(availableEnd, Math.max(startS, endS));
    if (hi <= lo) return;
    setPlaying(false);
    animationClock.setRate(playbackRateForSpan(hi - lo));
    animationClock.setRange(lo, hi);
    if (!playing) {
      animationClock.setPosition(hi);
    }
  };

  const setFromInput = (seconds: number): void => apply(seconds, selected[1]);
  const setToInput = (seconds: number): void => apply(selected[0], seconds);

  return (
    <section className="panel range" aria-label="Observation range">
      <p className="muted small">Observations from {formatObservedSpan(availFrom, availTo)}</p>
      <div className="range-fields">
        <div className="range-field">
          <span>From</span>
          {sameDay ? (
            <TimeField
              epoch={epoch}
              seconds={selected[0]}
              min={availableStart}
              max={selected[1]}
              onChange={setFromInput}
              label="Range start"
            />
          ) : (
            <DateTimeField
              epoch={epoch}
              seconds={selected[0]}
              min={availableStart}
              max={selected[1]}
              onChange={setFromInput}
              label="Range start"
            />
          )}
        </div>
        <div className="range-field">
          <span>To</span>
          {sameDay ? (
            <TimeField
              epoch={epoch}
              seconds={selected[1]}
              min={selected[0]}
              max={availableEnd}
              onChange={setToInput}
              label="Range end"
            />
          ) : (
            <DateTimeField
              epoch={epoch}
              seconds={selected[1]}
              min={selected[0]}
              max={availableEnd}
              onChange={setToInput}
              label="Range end"
            />
          )}
        </div>
      </div>
    </section>
  );
}

function TimeField({
  epoch,
  seconds,
  min,
  max,
  onChange,
  label,
}: {
  epoch: Date;
  seconds: number;
  min: number;
  max: number;
  onChange: (seconds: number) => void;
  label: string;
}): React.JSX.Element {
  const instant = new Date(epoch.getTime() + seconds * 1000);
  const wall = toManilaWallTime(instant);
  return (
    <input
      type="time"
      aria-label={label}
      value={manilaTimeInput(instant)}
      min={manilaTimeInput(new Date(epoch.getTime() + min * 1000))}
      max={manilaTimeInput(new Date(epoch.getTime() + max * 1000))}
      onChange={(event) => {
        const [hour, minute] = event.target.value.split(':').map(Number);
        if (hour === undefined || minute === undefined) return;
        const next = fromManilaWallTime({ ...wall, hour, minute, second: 0 });
        onChange((next.getTime() - epoch.getTime()) / 1000);
      }}
    />
  );
}

function DateTimeField({
  epoch,
  seconds,
  min,
  max,
  onChange,
  label,
}: {
  epoch: Date;
  seconds: number;
  min: number;
  max: number;
  onChange: (seconds: number) => void;
  label: string;
}): React.JSX.Element {
  const instant = new Date(epoch.getTime() + seconds * 1000);
  const wall = toManilaWallTime(instant);
  return (
    <span className="range-datetime">
      <input
        type="date"
        aria-label={`${label} date`}
        value={manilaDateInput(instant)}
        min={manilaDateInput(new Date(epoch.getTime() + min * 1000))}
        max={manilaDateInput(new Date(epoch.getTime() + max * 1000))}
        onChange={(event) => {
          const [year, month, day] = event.target.value.split('-').map(Number);
          if (year === undefined || month === undefined || day === undefined) return;
          const next = fromManilaWallTime({ ...wall, year, month, day });
          onChange((next.getTime() - epoch.getTime()) / 1000);
        }}
      />
      <input
        type="time"
        aria-label={`${label} time`}
        value={manilaTimeInput(instant)}
        onChange={(event) => {
          const [hour, minute] = event.target.value.split(':').map(Number);
          if (hour === undefined || minute === undefined) return;
          const next = fromManilaWallTime({ ...wall, hour, minute, second: 0 });
          onChange((next.getTime() - epoch.getTime()) / 1000);
        }}
      />
    </span>
  );
}
