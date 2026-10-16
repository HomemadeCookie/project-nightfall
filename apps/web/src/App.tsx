import { useEffect, useState } from "react";
import { useBundle } from "./data/api";
import type { Bundle } from "./data/types";
import { type StringKey, useLang } from "./i18n";
import { DataPage } from "./pages/DataPage";
import { Fuel } from "./pages/Fuel";
import { Home } from "./pages/Home";
import { Ports } from "./pages/Ports";
import { Prices } from "./pages/Prices";
import { Record } from "./pages/Record";
import { Sea } from "./pages/Sea";
import { Storms } from "./pages/Storms";
import { Supply } from "./pages/Supply";

export const ROUTES: { path: string; label: StringKey }[] = [
  { path: "today", label: "today" },
  { path: "fuel", label: "fuel" },
  { path: "ports", label: "ports" },
  { path: "sea", label: "sea" },
  { path: "prices", label: "prices" },
  { path: "supply", label: "supply" },
  { path: "storms", label: "storms" },
  { path: "record", label: "record" },
  { path: "data", label: "data" },
];

export function routeFromHash(hash: string): string {
  const p = hash.replace(/^#\/?/, "").split("?")[0] ?? "";
  return ROUTES.some((r) => r.path === p) ? p : "today";
}

function useRoute(): string {
  const [route, setRoute] = useState(() => routeFromHash(window.location.hash));
  useEffect(() => {
    const on = () => setRoute(routeFromHash(window.location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

function useRegion(): [string, (r: string) => void] {
  const [region, setRegion] = useState(() => {
    try {
      return localStorage.getItem("region") ?? "NCR";
    } catch {
      return "NCR";
    }
  });
  return [
    region,
    (r) => {
      setRegion(r);
      try {
        localStorage.setItem("region", r);
      } catch {
        /* ignore */
      }
    },
  ];
}

function Page({ route, bundle }: { route: string; bundle: Bundle }) {
  const [region, setRegion] = useRegion();
  switch (route) {
    case "fuel":
      return <Fuel bundle={bundle} />;
    case "ports":
      return <Ports bundle={bundle} />;
    case "sea":
      return <Sea bundle={bundle} />;
    case "prices":
      return <Prices bundle={bundle} />;
    case "supply":
      return <Supply bundle={bundle} />;
    case "storms":
      return <Storms bundle={bundle} />;
    case "record":
      return <Record bundle={bundle} />;
    case "data":
      return <DataPage bundle={bundle} />;
    default:
      return <Home bundle={bundle} region={region} setRegion={setRegion} />;
  }
}

export function App() {
  const state = useBundle();
  const route = useRoute();
  const { lang, setLang, t } = useLang();

  return (
    <>
      <a className="skip" href="#main">
        {t("skip")}
      </a>
      <header className="top">
        <div className="top-row">
          <h1>
            <a href="#/today">Nightfall PH</a>
          </h1>
          <label className="lang">
            <span className="sr">{t("language")}</span>
            <select value={lang} onChange={(e) => setLang(e.target.value as "en" | "fil")}>
              <option value="en">English</option>
              <option value="fil">Filipino</option>
            </select>
          </label>
        </div>
        <nav aria-label="Sections">
          {ROUTES.map((r) => (
            <a key={r.path} href={`#/${r.path}`} aria-current={route === r.path ? "page" : undefined}>
              {t(r.label)}
            </a>
          ))}
        </nav>
      </header>
      {state.status === "ready" && state.bundle.manifest.banner ? (
        <div className="banner" role="note">
          {state.bundle.manifest.banner}
        </div>
      ) : null}
      <main id="main">
        {state.status === "loading" ? (
          // biome-ignore lint/a11y/useSemanticElements: <output> is for form results; a loading notice is a plain live status
          <p role="status">{t("loading")}</p>
        ) : null}
        {state.status === "error" ? (
          <p role="alert" className="error">
            {state.message}
          </p>
        ) : null}
        {state.status === "ready" ? <Page route={route} bundle={state.bundle} /> : null}
      </main>
      <footer className="foot">
        Free public data, no tracking. Not financial or safety advice; follow PAGASA and Coast Guard
        bulletins.
      </footer>
    </>
  );
}
