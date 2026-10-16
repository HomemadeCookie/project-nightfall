import { escapeHtml, findRegion, fuelAdvice, regionAdvice } from "../src/advice";
import { handleCallback, handleMessage, handleUpdate, parseCommand } from "../src/commands";
import { getUser, recordFeedback, saveUser, subscribers } from "../src/store";
import type { Answer, Button, Deps, KV, Region } from "../src/types";

class FakeKV implements KV {
  data = new Map<string, string>();
  async get(k: string) {
    return this.data.get(k) ?? null;
  }
  async put(k: string, v: string) {
    this.data.set(k, v);
  }
  async delete(k: string) {
    this.data.delete(k);
  }
  async list({ prefix }: { prefix: string }) {
    return {
      keys: [...this.data.keys()].filter((k) => k.startsWith(prefix)).map((name) => ({ name })),
      list_complete: true,
    };
  }
}

const REGIONS: Region[] = [
  { region_code: "NCR", name: "National Capital Region", short: "Metro Manila" },
  { region_code: "V", name: "Bicol Region", short: "Bicol" },
  { region_code: "VII", name: "Central Visayas", short: "Central Visayas" },
  { region_code: "VIII", name: "Eastern Visayas", short: "Eastern Visayas" },
];

const ncr: Answer = {
  question_id: "retail.stock_up",
  scope: { region: "NCR" },
  verdict: "stock_up",
  confidence: "low",
  data_through: "2026-10-15",
  text: {
    en: "Metro Manila: consider stocking up on rice.",
    fil: "Metro Manila: magandang mag-imbak ng bigas.",
  },
  value: {
    items: [
      {
        item: "rice",
        label_en: "Rice",
        label_fil: "Bigas",
        verdict: "stock_up",
        reasons_en: ["Rice <may> get pricier."],
        reasons_fil: ["Malamang tumaas ang bigas."],
      },
      {
        item: "sugar",
        label_en: "Sugar",
        label_fil: "Asukal",
        verdict: "normal",
        reasons_en: [],
        reasons_fil: [],
      },
    ],
  },
};
const fuel: Answer[] = [
  {
    question_id: "fuel.next_week",
    scope: { product: "diesel" },
    verdict: "up",
    confidence: "low",
    text: { en: "Diesel looks set to rise.", fil: "Tataas ang diesel." },
    value: {},
  },
];

function setup(files: Record<string, unknown> = {}) {
  const sent: { chatId: number; html: string; buttons?: Button[][] }[] = [];
  const callbacks: string[] = [];
  const kv = new FakeKV();
  const data: Record<string, unknown> = {
    "answers/retail.stock_up.json": [ncr],
    "answers/fuel.next_week.json": fuel,
    "data/reference.json": { regions: REGIONS },
    ...files,
  };
  const deps: Deps = {
    kv,
    getJson: async <T>(p: string) => (data[p] as T | undefined) ?? null,
    send: async (chatId, html, buttons) => {
      sent.push({ chatId, html, buttons });
    },
    answerCallback: async (id) => {
      callbacks.push(id);
    },
  };
  return { deps, kv, sent, callbacks };
}

describe("parsing", () => {
  it("parses commands with arguments and bot suffixes", () => {
    expect(parseCommand("/region Bicol")).toEqual({ cmd: "region", arg: "Bicol" });
    expect(parseCommand("/Advice@NightfallBot")).toEqual({ cmd: "advice", arg: "" });
    expect(parseCommand("hello")).toBeNull();
  });

  it("finds regions by code, name, or partial text", () => {
    expect(findRegion("ncr", REGIONS)?.region_code).toBe("NCR");
    expect(findRegion("Region V", REGIONS)?.region_code).toBe("V");
    expect(findRegion("metro", REGIONS)?.region_code).toBe("NCR");
    expect(findRegion("visayas", REGIONS)).toBeDefined();
    expect(findRegion("atlantis", REGIONS)).toBeUndefined();
    expect(findRegion("  ", REGIONS)).toBeUndefined();
  });
});

describe("advice text", () => {
  it("lists only items that need action and escapes HTML", () => {
    const html = regionAdvice(ncr, REGIONS[0], "en");
    expect(html).toContain("Rice");
    expect(html).not.toContain("Sugar");
    expect(html).toContain("&lt;may&gt;");
    expect(html).toContain("Data through 2026-10-15");
    expect(html).toContain("Guidance, not a guarantee");
  });

  it("speaks Filipino and says so when there is nothing to do", () => {
    expect(regionAdvice(ncr, REGIONS[0], "fil")).toContain("Mag-imbak");
    const quiet = { ...ncr, value: { items: [] } };
    expect(regionAdvice(quiet, REGIONS[0], "en")).toContain("Nothing unusual");
    expect(regionAdvice(undefined, undefined, "fil")).toContain("Wala pang datos");
  });

  it("renders fuel direction and handles absence", () => {
    expect(fuelAdvice(fuel, "en")).toContain("Diesel looks set to rise.");
    expect(fuelAdvice([], "en")).toContain("No data yet");
    expect(escapeHtml("<b>&")).toBe("&lt;b&gt;&amp;");
  });
});

describe("conversation", () => {
  it("greets with a region keyboard", async () => {
    const { deps, sent } = setup();
    await handleMessage(1, "/start", deps);
    expect(sent[0]?.buttons?.flat().map((b) => b.data)).toEqual(["r:NCR", "r:V", "r:VII", "r:VIII"]);
  });

  it("gives advice for the saved region, with feedback buttons", async () => {
    const { deps, sent } = setup();
    await handleMessage(1, "/advice", deps);
    expect(sent[0]?.html).toContain("Metro Manila");
    expect(sent[0]?.buttons?.[0]?.map((b) => b.data)).toEqual(["fb:up", "fb:down"]);
  });

  it("sets region and language, and uses them", async () => {
    const { deps, sent, kv } = setup({
      "answers/retail.stock_up.json": [
        ncr,
        {
          ...ncr,
          scope: { region: "V" },
          text: { en: "Bicol: fine.", fil: "Bicol: ayos." },
          value: { items: [] },
        },
      ],
    });
    await handleMessage(7, "/region bicol", deps);
    await handleMessage(7, "/lang fil", deps);
    await handleMessage(7, "/advice", deps);
    expect(await getUser(kv, 7)).toMatchObject({ region: "V", lang: "fil" });
    expect(sent.at(-1)?.html).toContain("Bicol: ayos.");
  });

  it("rejects an unknown region and a bad language politely", async () => {
    const { deps, sent, kv } = setup();
    await handleMessage(1, "/region atlantis", deps);
    expect(sent[0]?.html).toContain("Region not found");
    await handleMessage(1, "/lang klingon", deps);
    expect(sent[1]?.html).toContain("Use /lang");
    expect((await getUser(kv, 1)).region).toBe("NCR");
  });

  it("subscribes, lists subscribers, and unsubscribes", async () => {
    const { deps, kv } = setup();
    await handleMessage(1, "/subscribe", deps);
    await handleMessage(2, "/region v", deps);
    expect((await subscribers(kv)).map((s) => s.chatId)).toEqual([1]);
    await handleMessage(1, "/unsubscribe", deps);
    expect(await subscribers(kv)).toEqual([]);
  });

  it("forgets everything on request", async () => {
    const { deps, kv } = setup();
    await saveUser(kv, 5, { region: "V", subscribed: true });
    await handleMessage(5, "/forget", deps);
    expect(kv.data.has("u:5")).toBe(false);
  });

  it("shows help for unknown input", async () => {
    const { deps, sent } = setup();
    await handleMessage(1, "what is this", deps);
    await handleMessage(1, "/nonsense", deps);
    expect(sent).toHaveLength(2);
    expect(sent[0]?.html).toContain("/advice");
  });

  it("handles region buttons and feedback buttons", async () => {
    const { deps, sent, callbacks, kv } = setup();
    await handleCallback(9, "cb1", "r:NCR", deps);
    expect(callbacks).toEqual(["cb1"]);
    expect(sent.map((m) => m.html).join("\n")).toContain("Metro Manila");
    await handleCallback(9, "cb2", "fb:up", deps);
    await handleCallback(9, "cb3", "fb:down", deps);
    await handleCallback(9, "cb4", "fb:up", deps);
    expect(kv.data.get("fb:up")).toBe("2");
    expect(kv.data.get("fb:down")).toBe("1");
    await handleCallback(9, "cb5", "r:NOPE", deps); // unknown region: ignored, no crash
  });

  it("routes Telegram updates to the right handler", async () => {
    const { deps, sent } = setup();
    await handleUpdate({ message: { chat: { id: 3 }, text: "/fuel" } }, deps);
    await handleUpdate({ callback_query: { id: "x", data: "fb:up", message: { chat: { id: 3 } } } }, deps);
    await handleUpdate({}, deps);
    expect(sent[0]?.html).toContain("Diesel looks set to rise.");
    expect(sent).toHaveLength(2);
  });

  it("counts feedback without recording who voted", async () => {
    const kv = new FakeKV();
    await recordFeedback(kv, "down");
    expect([...kv.data.keys()]).toEqual(["fb:down"]);
  });
});
