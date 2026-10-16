import { type ReactNode, createContext, useCallback, useContext, useMemo, useState } from "react";

export type Lang = "en" | "fil";

const STRINGS = {
  today: { en: "Today", fil: "Ngayon" },
  fuel: { en: "Fuel", fil: "Gasolina" },
  ports: { en: "Ports", fil: "Pantalan" },
  sea: { en: "Sea routes", fil: "Ruta sa dagat" },
  prices: { en: "Prices", fil: "Presyo" },
  supply: { en: "Supply", fil: "Suplay" },
  storms: { en: "Storms", fil: "Bagyo" },
  record: { en: "Track record", fil: "Rekord" },
  data: { en: "Data & licences", fil: "Datos at lisensya" },
  map: { en: "Live map", fil: "Mapa" },
  region: { en: "Your region", fil: "Inyong rehiyon" },
  stockUp: { en: "Should I stock up this week?", fil: "Dapat ba akong mag-imbak ngayong linggo?" },
  confidence: { en: "Confidence", fil: "Tiwala" },
  dataThrough: { en: "Data through", fil: "Datos hanggang" },
  why: { en: "Why", fil: "Bakit" },
  caveats: { en: "Limits of this answer", fil: "Limitasyon ng sagot" },
  loading: { en: "Loading the latest signals…", fil: "Kinukuha ang pinakabagong datos…" },
  noData: { en: "No data yet", fil: "Wala pang datos" },
  skip: { en: "Skip to content", fil: "Laktawan papunta sa nilalaman" },
  language: { en: "Language", fil: "Wika" },
  tracked: { en: "Storms tracked", fil: "Mga bagyong sinusubaybayan" },
  none: { en: "none", fil: "wala" },
} as const;

export type StringKey = keyof typeof STRINGS;

interface Ctx {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (k: StringKey) => string;
}

const LangContext = createContext<Ctx>({ lang: "en", setLang: () => {}, t: (k) => STRINGS[k].en });

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem("lang");
    if (saved === "en" || saved === "fil") return saved;
  } catch {
    /* storage unavailable (private window): fall through */
  }
  return typeof navigator !== "undefined" && /^(fil|tl)/i.test(navigator.language) ? "fil" : "en";
}

export function LangProvider({ children, initial }: { children: ReactNode; initial?: Lang }) {
  const [lang, setLangState] = useState<Lang>(initial ?? initialLang());
  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem("lang", l);
    } catch {
      /* ignore */
    }
  }, []);
  const value = useMemo<Ctx>(() => ({ lang, setLang, t: (k) => STRINGS[k][lang] }), [lang, setLang]);
  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export const useLang = (): Ctx => useContext(LangContext);
