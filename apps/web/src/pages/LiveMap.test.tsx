import { fireEvent, render, screen, within } from "@testing-library/react";
import { LangProvider } from "../i18n";
import { bundle } from "../test-fixtures";
import { LiveMap, buildPlaces } from "./LiveMap";

const renderMap = () =>
  render(
    <LangProvider initial="en">
      <LiveMap bundle={bundle} />
    </LangProvider>,
  );

describe("buildPlaces", () => {
  it("compiles regions, ports, routes and storms from the answers", () => {
    const places = buildPlaces(bundle, "en");
    const kinds = new Set(places.map((p) => p.kind));
    expect(kinds).toEqual(new Set(["region", "port", "route", "storm"]));
    const ncr = places.find((p) => p.id === "region:NCR");
    expect(ncr?.tone).toBe("alert");
    expect(ncr?.lines.join(" ")).toContain("Rice");
    expect(places.find((p) => p.id === "route:matnog-allen")?.lines).toContain("72 h: Likely");
    expect(places.find((p) => p.id === "port:MNL")?.significant).toBe(true); // elevated
    expect(places.find((p) => p.id === "region:V")?.significant).toBe(false); // normal
  });

  it("speaks Filipino when asked", () => {
    const ncr = buildPlaces(bundle, "fil").find((p) => p.id === "region:NCR");
    expect(ncr?.headline).toContain("Filipino");
    expect(ncr?.lines.join(" ")).toContain("Bigas");
  });
});

describe("LiveMap", () => {
  it("shows a place's details on hover and clears them on leave", () => {
    renderMap();
    const route = screen.getByRole("button", { name: /Matnog - Allen: Likely/ });
    fireEvent.mouseEnter(route);
    const detail = screen
      .getByRole("heading", { level: 3, name: "Matnog - Allen" })
      .closest("section") as HTMLElement;
    expect(within(detail).getByText("English text for ferry.suspension")).toBeInTheDocument();
    expect(within(detail).getByText(/Peak wave 4.5 m/)).toBeInTheDocument();
    fireEvent.mouseLeave(route);
    expect(screen.getByRole("heading", { level: 3, name: "Pick a place" })).toBeInTheDocument();
  });

  it("pins a place on click so it stays after the pointer leaves, and Escape unpins", () => {
    renderMap();
    const port = screen.getByRole("button", { name: /Manila port: Elevated/ });
    fireEvent.click(port);
    fireEvent.mouseLeave(port);
    expect(screen.getByRole("heading", { level: 3, name: "Manila" })).toBeInTheDocument();
    expect(screen.getByText(/pinned/)).toBeInTheDocument();
    fireEvent.keyDown(port, { key: "Escape" });
    expect(screen.getByRole("heading", { level: 3, name: "Pick a place" })).toBeInTheDocument();
  });

  it("works from the keyboard", () => {
    renderMap();
    const region = screen.getByRole("button", { name: /National Capital Region: Stock up/ });
    fireEvent.focus(region);
    expect(screen.getByRole("heading", { level: 3, name: "National Capital Region" })).toBeInTheDocument();
    fireEvent.keyDown(region, { key: "Enter" });
    fireEvent.blur(region);
    expect(screen.getByRole("heading", { level: 3, name: "National Capital Region" })).toBeInTheDocument(); // pinned
  });

  it("lists significant places, most urgent first, and the list drives the map", () => {
    renderMap();
    const list = screen
      .getByRole("heading", { level: 3, name: /Significant now/ })
      .closest("section") as HTMLElement;
    const items = within(list).getAllByRole("button");
    expect(items.length).toBeGreaterThanOrEqual(3);
    expect(items[0]).toHaveTextContent(/Stock up|Likely/); // alerts before watches
    expect(within(list).queryByText("Bicol Region")).toBeNull(); // normal places are not listed
    fireEvent.mouseEnter(within(list).getByText("CHAMPI-26"));
    expect(screen.getByRole("heading", { level: 3, name: "CHAMPI-26" })).toBeInTheDocument();
  });

  it("toggles layers", () => {
    const { container } = renderMap();
    expect(container.querySelectorAll(".lm-route")).toHaveLength(1);
    fireEvent.click(screen.getByLabelText(/Ferry route/));
    expect(container.querySelectorAll(".lm-route")).toHaveLength(0);
    fireEvent.click(screen.getByLabelText(/Port/));
    expect(container.querySelectorAll(".lm-port")).toHaveLength(0);
  });
});
