/**
 * Time, in two parts.
 *
 * Presentation: invariant 6 puts UTC in storage and Asia/Manila on screen, and this is the one
 * place the conversion happens. Agricultural and typhoon-preparation decisions are made
 * against the local calendar, so a stray browser-locale timestamp would be wrong in a way that
 * looks right to the developer and wrong to the user.
 *
 * Animation: exactly one `requestAnimationFrame` loop exists for the whole app
 * (`.cursorrules` § 6). Layers never schedule their own redraw, and the loop publishes to
 * subscribers rather than to React state, because a 60 Hz re-render would cost more than the
 * frame it is trying to draw.
 */

export const PH_TIME_ZONE = 'Asia/Manila';

/** Asia/Manila is UTC+8 year-round. The conversion boundary stays in this file. */
export const MANILA_OFFSET_MS = 8 * 60 * 60 * 1000;

const MANILA_FORMAT = new Intl.DateTimeFormat('en-GB', {
  timeZone: PH_TIME_ZONE,
  year: 'numeric',
  month: 'short',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

const MANILA_TIME_ONLY = new Intl.DateTimeFormat('en-GB', {
  timeZone: PH_TIME_ZONE,
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

/** Format an instant in Philippine local time, labelled so the zone is never ambiguous. */
export function formatManila(instant: Date): string {
  return `${MANILA_FORMAT.format(instant)} PHT`;
}

export function formatManilaTime(instant: Date): string {
  return `${MANILA_TIME_ONLY.format(instant)} PHT`;
}

export interface ManilaWallTime {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
}

/** Break an instant into Philippine civil time. Storage stays UTC. */
export function toManilaWallTime(instant: Date): ManilaWallTime {
  const shifted = new Date(instant.getTime() + MANILA_OFFSET_MS);
  return {
    year: shifted.getUTCFullYear(),
    month: shifted.getUTCMonth() + 1,
    day: shifted.getUTCDate(),
    hour: shifted.getUTCHours(),
    minute: shifted.getUTCMinutes(),
    second: shifted.getUTCSeconds(),
  };
}

/** Compose a UTC instant from Philippine civil time. */
export function fromManilaWallTime(parts: ManilaWallTime): Date {
  return new Date(
    Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute, parts.second) -
      MANILA_OFFSET_MS,
  );
}

function pad2(value: number): string {
  return String(value).padStart(2, '0');
}

export function manilaTimeInput(instant: Date): string {
  const wall = toManilaWallTime(instant);
  return `${pad2(wall.hour)}:${pad2(wall.minute)}`;
}

export function manilaDateInput(instant: Date): string {
  const wall = toManilaWallTime(instant);
  return `${wall.year}-${pad2(wall.month)}-${pad2(wall.day)}`;
}

/**
 * Plain-language observed span in Manila time.
 *
 * A few minutes of one day reads as a clock range. Separate years read as years, because
 * "2019-01-01 00:00 PHT – 2024-12-31 23:59 PHT" is how a missing archive pretends to be data.
 */
export function formatObservedSpan(from: Date, to: Date): string {
  const start = toManilaWallTime(from);
  const end = toManilaWallTime(to);
  if (
    start.year !== end.year &&
    start.month === 1 &&
    start.day === 1 &&
    end.month === 12 &&
    end.day === 31
  ) {
    return `${start.year}–${end.year}`;
  }
  if (start.year === end.year && start.month === end.month && start.day === end.day) {
    return (
      `${start.day} ${manilaMonth(start.month)} ${start.year}, ` +
      `${pad2(start.hour)}:${pad2(start.minute)}–${pad2(end.hour)}:${pad2(end.minute)} PHT`
    );
  }
  return `${formatManila(from)} – ${formatManila(to)}`;
}

function manilaMonth(month: number): string {
  return (
    ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][
      month - 1
    ] ?? '???'
  );
}

/** Human-readable age. Used for freshness, where "3 hours ago" is the actual message. */
export function formatAge(from: Date, to: Date = new Date()): string {
  const seconds = Math.max(0, Math.round((to.getTime() - from.getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

export type ClockListener = (artifactSeconds: number) => void;
export type RangeListener = (start: number, end: number) => void;

/**
 * The single animation clock.
 *
 * Holds a position in *artifact* seconds — offsets from the epoch the manifest publishes — not
 * wall-clock time, so playback is independent of when the page happens to be open.
 */
export class AnimationClock {
  private position = 0;
  private rangeStart = 0;
  private rangeEnd = 0;
  private rate: number;
  private playing = false;
  private frame: number | null = null;
  private lastFrameMs: number | null = null;
  private readonly listeners = new Set<ClockListener>();
  private readonly rangeListeners = new Set<RangeListener>();

  constructor(rate: number) {
    this.rate = rate;
  }

  setRate(rate: number): void {
    this.rate = rate;
  }

  get playbackRate(): number {
    return this.rate;
  }

  setRange(start: number, end: number): void {
    this.rangeStart = start;
    this.rangeEnd = end;
    if (this.position < start || this.position > end) {
      this.position = start;
    }
    for (const listener of this.rangeListeners) {
      listener(start, end);
    }
    this.publish();
    // Playback is usually requested before the artifacts have finished decoding, so the
    // request is honoured here rather than dropped for want of a span to play.
    this.ensureLoop();
  }

  get range(): readonly [number, number] {
    return [this.rangeStart, this.rangeEnd];
  }

  setPosition(seconds: number): void {
    this.position = Math.min(this.rangeEnd, Math.max(this.rangeStart, seconds));
    this.publish();
  }

  get currentPosition(): number {
    return this.position;
  }

  get isPlaying(): boolean {
    return this.playing;
  }

  /** Records the intent to play. The loop starts as soon as there is a span to play over. */
  play(): void {
    this.playing = true;
    this.ensureLoop();
  }

  pause(): void {
    this.playing = false;
    if (this.frame !== null) {
      cancelAnimationFrame(this.frame);
      this.frame = null;
    }
  }

  subscribe(listener: ClockListener): () => void {
    this.listeners.add(listener);
    listener(this.position);
    return () => {
      this.listeners.delete(listener);
    };
  }

  /**
   * Subscribe to changes in the playable span. Called immediately with the current range so a
   * subscriber that mounts after the artifacts have decoded is not left showing an empty span.
   */
  subscribeRange(listener: RangeListener): () => void {
    this.rangeListeners.add(listener);
    listener(this.rangeStart, this.rangeEnd);
    return () => {
      this.rangeListeners.delete(listener);
    };
  }

  private ensureLoop(): void {
    if (!this.playing || this.frame !== null || this.rangeEnd <= this.rangeStart) return;
    this.lastFrameMs = null;
    this.frame = requestAnimationFrame(this.tick);
  }

  private readonly tick = (nowMs: number): void => {
    if (!this.playing) return;
    const elapsedMs = this.lastFrameMs === null ? 0 : nowMs - this.lastFrameMs;
    this.lastFrameMs = nowMs;
    this.position += (elapsedMs / 1000) * this.rate;
    if (this.position > this.rangeEnd) {
      this.position = this.rangeStart;
    }
    this.publish();
    this.frame = requestAnimationFrame(this.tick);
  };

  private publish(): void {
    for (const listener of this.listeners) {
      listener(this.position);
    }
  }
}
