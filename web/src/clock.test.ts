import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  AnimationClock,
  formatAge,
  formatManila,
  formatManilaTime,
  formatObservedSpan,
  fromManilaWallTime,
  manilaTimeInput,
  toManilaWallTime,
} from './clock';

describe('Manila presentation', () => {
  it('renders an instant in Philippine time regardless of the host zone', () => {
    // 18:30 UTC is the following day in Manila (UTC+8). Getting this wrong would shift a
    // typhoon-window reading by a calendar day while looking entirely plausible.
    // The month abbreviation is left to ICU, which spells September differently across
    // versions; the day, the time and the labelled zone are what must not drift.
    const instant = new Date('2026-09-11T18:30:00Z');
    expect(formatManila(instant)).toMatch(/^12 Sept? 2026, 02:30 PHT$/);
    expect(formatManilaTime(instant)).toBe('02:30:00 PHT');
  });

  it('never presents a bare local time without its zone', () => {
    expect(formatManila(new Date('2026-01-01T00:00:00Z'))).toContain('PHT');
    expect(formatManilaTime(new Date('2026-01-01T00:00:00Z'))).toContain('PHT');
  });
});

describe('Manila wall-time conversion', () => {
  it('round-trips a UTC instant through Philippine civil time', () => {
    const instant = new Date('2026-09-12T16:05:00Z');
    const wall = toManilaWallTime(instant);
    expect(wall).toEqual({ year: 2026, month: 9, day: 13, hour: 0, minute: 5, second: 0 });
    expect(fromManilaWallTime(wall).toISOString()).toBe(instant.toISOString());
    expect(manilaTimeInput(instant)).toBe('00:05');
  });
});

describe('formatObservedSpan', () => {
  it('collapses a single Manila day to a clock range', () => {
    expect(
      formatObservedSpan(new Date('2026-09-11T19:42:00Z'), new Date('2026-09-11T19:45:00Z')),
    ).toBe('12 Sep 2026, 03:42–03:45 PHT');
  });

  it('names whole years when that is the honest span', () => {
    expect(
      formatObservedSpan(
        new Date('2019-01-01T00:00:00+08:00'),
        new Date('2024-12-31T23:59:00+08:00'),
      ),
    ).toBe('2019–2024');
  });
});

describe('formatAge', () => {
  const now = new Date('2026-09-11T12:00:00Z');

  it('scales the unit to the age', () => {
    expect(formatAge(new Date('2026-09-11T11:59:30Z'), now)).toBe('30s ago');
    expect(formatAge(new Date('2026-09-11T11:40:00Z'), now)).toBe('20m ago');
    expect(formatAge(new Date('2026-09-11T05:00:00Z'), now)).toBe('7h ago');
    expect(formatAge(new Date('2026-09-08T12:00:00Z'), now)).toBe('3d ago');
  });

  it('does not report a negative age from a clock skew', () => {
    expect(formatAge(new Date('2026-09-11T12:05:00Z'), now)).toBe('0s ago');
  });
});

describe('AnimationClock', () => {
  let frames: FrameRequestCallback[] = [];

  beforeEach(() => {
    frames = [];
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      frames.push(callback);
      return frames.length;
    });
    vi.stubGlobal('cancelAnimationFrame', () => {
      frames = [];
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  /** Run one frame at a given timestamp, as the browser would. */
  function advance(atMs: number): void {
    const pending = frames;
    frames = [];
    for (const frame of pending) frame(atMs);
  }

  it('publishes the current position to subscribers on subscribe', () => {
    const clock = new AnimationClock(1);
    clock.setRange(100, 200);
    const seen: number[] = [];
    clock.subscribe((seconds) => seen.push(seconds));
    expect(seen).toEqual([100]);
  });

  it('keeps the playable domain equal to the span it was given', () => {
    // The slider must not be able to leave the baked min/max.
    const clock = new AnimationClock(1);
    clock.setRange(12, 84);
    expect(clock.range).toEqual([12, 84]);
    clock.setPosition(12);
    expect(clock.currentPosition).toBe(12);
    clock.setPosition(84);
    expect(clock.currentPosition).toBe(84);
  });

  it('clamps a scrub to the range', () => {
    const clock = new AnimationClock(1);
    clock.setRange(100, 200);
    clock.setPosition(500);
    expect(clock.currentPosition).toBe(200);
    clock.setPosition(-10);
    expect(clock.currentPosition).toBe(100);
  });

  it('honours a play requested before the artifacts decoded', () => {
    // The common case on load: the UI asks to play while the range is still empty. Dropping
    // that request would leave the button reading "Pause" over a clock that never moved.
    const clock = new AnimationClock(10);
    clock.play();
    expect(frames).toHaveLength(0);

    clock.setRange(0, 600);
    expect(frames).toHaveLength(1);

    advance(1000);
    advance(2000);
    expect(clock.currentPosition).toBeCloseTo(10, 6);
  });

  it('advances at the configured rate and wraps at the end of the span', () => {
    const clock = new AnimationClock(100);
    clock.setRange(0, 150);
    clock.play();
    advance(0);
    advance(1000);
    expect(clock.currentPosition).toBeCloseTo(100, 6);
    advance(2000);
    expect(clock.currentPosition).toBe(0);
  });

  it('stops scheduling frames once paused', () => {
    const clock = new AnimationClock(1);
    clock.setRange(0, 100);
    clock.play();
    advance(0);
    clock.pause();
    expect(clock.isPlaying).toBe(false);
    advance(1000);
    expect(clock.currentPosition).toBe(0);
  });

  it('reports a new range to range subscribers, including the current one on subscribe', () => {
    const clock = new AnimationClock(1);
    const seen: Array<[number, number]> = [];
    clock.subscribeRange((start, end) => seen.push([start, end]));
    expect(seen).toEqual([[0, 0]]);
    clock.setRange(5, 25);
    expect(seen.at(-1)).toEqual([5, 25]);
  });

  it('releases subscribers so a remounted component cannot leak a listener', () => {
    const clock = new AnimationClock(1);
    const seen: number[] = [];
    const unsubscribe = clock.subscribe((seconds) => seen.push(seconds));
    unsubscribe();
    clock.setRange(0, 10);
    expect(seen).toEqual([0]);
  });
});
