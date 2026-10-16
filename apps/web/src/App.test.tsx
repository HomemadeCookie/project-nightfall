import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { App, routeFromHash } from "./App";
import { LangProvider } from "./i18n";
import { answers, bundle, manifest } from "./test-fixtures";

function mockFetch(overrides: Record<string, unknown> = {}) {
  const files: Record<string, unknown> = {
    "manifest.json": manifest,
    "answers/index.json": answers,
    "data/fuel_weekly.json": bundle.fuel,
    "data/ports_daily.json": bundle.ports,
    "data/storms.json": bundle.storms,
    "data/reference.json": bundle.reference,
    "ph-regions.json": bundle.regionsGeo,
    ...overrides,
  };
  globalThis.fetch = vi.fn(async (url: RequestInfo | URL) => {
    const key = String(url);
    return key in files
      ? new Response(JSON.stringify(files[key]), { status: 200 })
      : new Response("not found", { status: 404 });
  }) as typeof fetch;
}

const renderApp = (initial: "en" | "fil" = "en") =>
  render(
    <LangProvider initial={initial}>
      <App />
    </LangProvider>,
  );

beforeEach(() => {
  window.location.hash = "";
  localStorage.clear();
});

describe("routing", () => {
  it("falls back to Today for unknown routes", () => {
    expect(routeFromHash("#/fuel")).toBe("fuel");
    expect(routeFromHash("#/nope")).toBe("today");
    expect(routeFromHash("")).toBe("today");
  });
});

describe("App", () => {
  it("shows the research banner and the stock-up advice for the saved region", async () => {
    mockFetch();
    renderApp();
    expect(await screen.findByText(/Research preview/)).toBeInTheDocument();
    expect(await screen.findByText("English text for retail.stock_up")).toBeInTheDocument();
    const rice = screen.getByText("Rice").closest("li");
    expect(rice).not.toBeNull();
    expect(within(rice as HTMLElement).getByText("Rice is likely to get pricier.")).toBeInTheDocument();
    expect(screen.queryByText("Sugar")).toBeNull(); // 'normal' items are not shown as advice
  });

  it("switches language and persists the choice", async () => {
    mockFetch();
    renderApp();
    await screen.findByText("English text for retail.stock_up");
    fireEvent.change(screen.getByLabelText("Language"), { target: { value: "fil" } });
    expect(await screen.findByText("Tekstong Filipino para sa retail.stock_up")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Gasolina" })).toBeInTheDocument();
    expect(localStorage.getItem("lang")).toBe("fil");
    expect(screen.getByText("Bigas")).toBeInTheDocument();
  });

  it("changes region and remembers it", async () => {
    mockFetch();
    renderApp();
    await screen.findByText("English text for retail.stock_up");
    fireEvent.change(screen.getByLabelText("Your region"), { target: { value: "V" } });
    expect(localStorage.getItem("region")).toBe("V");
  });

  it("navigates to each page without crashing", async () => {
    mockFetch();
    renderApp();
    await screen.findByText("English text for retail.stock_up");
    for (const [hash, heading] of [
      ["#/fuel", "Fuel"],
      ["#/ports", "Ports"],
      ["#/sea", "Sea routes"],
      ["#/prices", "Prices"],
      ["#/supply", "Supply"],
      ["#/storms", "Storms"],
      ["#/record", "Track record"],
      ["#/data", "Data & licences"],
    ] as const) {
      window.location.hash = hash;
      fireEvent(window, new HashChangeEvent("hashchange"));
      expect(await screen.findByRole("heading", { level: 2, name: heading })).toBeInTheDocument();
    }
  });

  it("marks answers that are for research use only", async () => {
    mockFetch({
      "answers/index.json": answers.map((a) =>
        a.question_id === "ferry.suspension" ? { ...a, commercial_ok: false } : a,
      ),
    });
    renderApp();
    await screen.findByText("English text for retail.stock_up");
    window.location.hash = "#/sea";
    fireEvent(window, new HashChangeEvent("hashchange"));
    await screen.findByRole("heading", { level: 2, name: "Sea routes" });
    expect(screen.getAllByText(/research use only/).length).toBeGreaterThan(0);
  });

  it("renders every page when most questions are absent (commercial mode)", async () => {
    mockFetch({
      "manifest.json": { ...manifest, mode: "commercial", banner: null },
      "answers/index.json": answers.filter((a) => a.question_id === "fuel.next_week"),
    });
    renderApp();
    expect(await screen.findByText("Diesel")).toBeInTheDocument(); // fuel shows as a stat tile on Today
    expect(screen.getByText("+₱2.80/L")).toBeInTheDocument();
    expect(screen.queryByText(/Research preview/)).toBeNull();
    for (const hash of [
      "#/today",
      "#/ports",
      "#/sea",
      "#/prices",
      "#/supply",
      "#/storms",
      "#/record",
      "#/data",
    ]) {
      window.location.hash = hash;
      fireEvent(window, new HashChangeEvent("hashchange"));
      expect((await screen.findAllByRole("heading", { level: 2 })).length).toBeGreaterThan(0);
    }
    expect(screen.getByText(/Commercial mode/)).toBeInTheDocument();
  });

  it("shows a clear error when nothing has been published", async () => {
    mockFetch({ "manifest.json": { empty: true } });
    renderApp();
    expect(await screen.findByRole("alert")).toHaveTextContent(/No data published yet/);
  });

  it("shows a clear error when the network fails", async () => {
    globalThis.fetch = vi.fn(async () => new Response("boom", { status: 500 })) as typeof fetch;
    renderApp();
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/HTTP 500/));
  });

  it("survives optional datasets being absent", async () => {
    mockFetch({ "data/fuel_weekly.json": undefined, "data/storms.json": undefined });
    // undefined bodies serialise to nothing; emulate absence with 404s instead
    globalThis.fetch = vi.fn(async (url: RequestInfo | URL) => {
      const k = String(url);
      if (k === "manifest.json") return new Response(JSON.stringify(manifest));
      if (k === "answers/index.json") return new Response(JSON.stringify(answers));
      return new Response("nope", { status: 404 });
    }) as typeof fetch;
    renderApp();
    expect(await screen.findByText("English text for retail.stock_up")).toBeInTheDocument();
  });

  it("exposes skip link, landmarks and the current page in the nav", async () => {
    mockFetch();
    renderApp();
    await screen.findByText("English text for retail.stock_up");
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main");
    expect(screen.getByRole("navigation", { name: "Sections" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Today" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("main")).toBeInTheDocument();
  });
});
