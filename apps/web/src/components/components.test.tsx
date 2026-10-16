import { render, screen } from "@testing-library/react";
import { bundle } from "../test-fixtures";
import { LineChart, Sparkline, niceRange } from "./Charts";
import { PhMap, kmToPx, makeProjection } from "./PhMap";

describe("LineChart", () => {
  const series = [
    {
      name: "Diesel",
      tone: "a" as const,
      points: [
        { x: "2026-09-07", y: 38 },
        { x: "2026-09-14", y: 40 },
        { x: "2026-09-21", y: 39 },
      ],
    },
  ];

  it("draws one line per series with an accessible summary", () => {
    const { container } = render(
      <LineChart label="Weekly cost" series={series} format={(n) => n.toFixed(0)} />,
    );
    expect(container.querySelectorAll("polyline")).toHaveLength(1);
    expect(screen.getByRole("img")).toHaveAccessibleName(/Weekly cost: Diesel latest 39/);
  });

  it("says so instead of drawing nonsense when there is too little data", () => {
    render(<LineChart label="x" series={[{ name: "a", tone: "a", points: [{ x: "2026-09-07", y: 1 }] }]} />);
    expect(screen.getByText(/Not enough data/)).toBeInTheDocument();
  });

  it("drops points with bad dates or values rather than drawing NaN", () => {
    const messy = [
      {
        name: "A",
        tone: "a" as const,
        points: [
          { x: "2026-09-07", y: 1 },
          { x: "2026-09-42", y: 2 },
          { x: "2026-09-14", y: Number.NaN },
          { x: "2026-09-21", y: 3 },
        ],
      },
    ];
    const { container } = render(<LineChart label="messy" series={messy} />);
    expect(container.querySelector("polyline")?.getAttribute("points")).not.toMatch(/NaN/);
    expect(container.querySelector("polyline")?.getAttribute("points")?.split(" ")).toHaveLength(2);
  });

  it("pads a flat range so the line is visible", () => {
    expect(niceRange(5, 5)).toEqual([4, 6]);
    const [lo, hi] = niceRange(0, 10);
    expect(lo).toBeLessThan(0);
    expect(hi).toBeGreaterThan(10);
  });

  it("renders a sparkline only with two or more points", () => {
    const { container, rerender } = render(<Sparkline values={[1]} label="s" />);
    expect(container.querySelector("svg")).toBeNull();
    rerender(<Sparkline values={[1, 2, 3]} label="s" />);
    expect(container.querySelector("svg")).not.toBeNull();
  });
});

describe("PhMap", () => {
  it("projects Philippine coordinates inside the viewBox", () => {
    const p = makeProjection(bundle.regionsGeo as GeoJSON.FeatureCollection);
    const pt = p([121, 14.6]);
    expect(pt).not.toBeNull();
    expect(pt?.[0]).toBeGreaterThan(0);
    expect(pt?.[1]).toBeGreaterThan(0);
  });

  it("converts kilometres to a positive pixel radius", () => {
    const p = makeProjection(bundle.regionsGeo as GeoJSON.FeatureCollection);
    const project = (c: [number, number]) => p(c) as [number, number] | null;
    const small = kmToPx(project, 14, 121, 50);
    const big = kmToPx(project, 14, 121, 200);
    expect(small).toBeGreaterThan(0);
    expect(big / small).toBeCloseTo(4, 0);
  });

  it("draws regions, ports, routes and storms, and renders nothing without geography", () => {
    const { container, rerender } = render(
      <PhMap
        geo={bundle.regionsGeo}
        ports={bundle.reference?.ports}
        storms={bundle.storms}
        routes={[
          {
            id: "r",
            label: "Route",
            line: [
              [12.58, 124.08],
              [12.5, 124.28],
            ],
            tone: "alert",
          },
        ]}
        label="map"
      />,
    );
    expect(container.querySelectorAll("path.region")).toHaveLength(2);
    expect(container.querySelectorAll("circle.port")).toHaveLength(1);
    expect(container.querySelector("path.route-alert")).not.toBeNull();
    expect(container.querySelector(".storm-label")?.textContent).toBe("CHAMPI-26");
    rerender(<PhMap geo={null} label="map" />);
    expect(container.querySelector("svg")).toBeNull();
  });
});
