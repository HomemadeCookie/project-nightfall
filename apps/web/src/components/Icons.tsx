// Small stroke icons (24x24, currentColor). Decorative: always paired with visible text.
const paths: Record<string, string> = {
  moon: "M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z",
  rice: "M3 11h18a9 9 0 0 1-18 0zM8 8c0-2 1.5-3 4-3s4 1 4 3M7 21h10",
  sugar: "M5 8l7-4 7 4v8l-7 4-7-4zM5 8l7 4 7-4M12 12v8",
  cooking_oil: "M10 3h4M10 3v4l-3 4v9h10v-9l-3-4V3M7 14h10",
  canned_noodles:
    "M5 6c0-1.5 3-2.5 7-2.5s7 1 7 2.5v12c0 1.5-3 2.5-7 2.5s-7-1-7-2.5zM5 6c0 1.5 3 2.5 7 2.5s7-1 7-2.5M5 12c0 1.5 3 2.5 7 2.5s7-1 7-2.5",
  water_light: "M12 3c3 4 6 7.5 6 11a6 6 0 0 1-12 0c0-3.5 3-7 6-11z",
  fuel: "M4 21V5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v16M3 21h12M6 9h6M14 10h2a2 2 0 0 1 2 2v4a1.5 1.5 0 0 0 3 0V8l-3-3",
  ship: "M3 17l2 4h14l2-4-9-3zM12 3v11M8 7h8l-1 4H9z",
  port: "M4 21V9l5-3v15M9 21V4h6v17M15 21v-8h5v8M2 21h20",
  storm: "M4 14a5 5 0 0 1 3-9 6 6 0 0 1 11 2 4 4 0 0 1 0 8H8M11 13l-2 4h4l-2 4",
  chart: "M4 20V4M4 20h16M8 16l4-5 3 3 5-6",
  globe:
    "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c2.5 2.5 3.5 6 3.5 9s-1 6.5-3.5 9c-2.5-2.5-3.5-6-3.5-9s1-6.5 3.5-9z",
  info: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 11v6M12 7.5v.5",
  arrow: "M5 12h14M13 6l6 6-6 6",
  up: "M12 19V5M6 11l6-6 6 6",
  down: "M12 5v14M6 13l6 6 6-6",
  flat: "M5 12h14",
  check: "M5 12l5 5 9-10",
  plane: "M3 13l7-2 4-8h2l-2 8 6 1 2-2h1l-1 4 1 4h-1l-2-2-6 1 2 8h-2l-4-8-7-2z",
};

export type IconName = keyof typeof paths;

export function Icon({ name, size = 20, className }: { name: string; size?: number; className?: string }) {
  const d = paths[name] ?? paths.info;
  return (
    <svg
      className={`icon ${className ?? ""}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={d} />
    </svg>
  );
}
