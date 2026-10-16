import { ageLabel, byQuestion, humanize, pct, peso, shortDate, text, tone, verdictLabel } from "./format";
import { answers } from "./test-fixtures";

describe("format", () => {
  it("maps verdicts to tones and never leaves an unknown verdict toneless", () => {
    expect(tone("normal")).toBe("ok");
    expect(tone("likely")).toBe("alert");
    expect(tone("elevated")).toBe("watch");
    expect(tone("no_call")).toBe("muted");
    expect(tone("something_new")).toBe("muted");
  });

  it("labels verdicts in both languages and falls back gracefully", () => {
    expect(verdictLabel("stock_up", "en")).toBe("Stock up");
    expect(verdictLabel("stock_up", "fil")).toBe("Mag-imbak");
    expect(verdictLabel("brand_new", "fil")).toBe("Brand new");
    expect(humanize("insufficient_data")).toBe("Insufficient data");
  });

  it("formats money and percentages", () => {
    expect(peso(1234.5)).toBe("₱1,234.50");
    expect(peso(38.31, 0)).toBe("₱38");
    expect(pct(0.0123)).toBe("+1.2%");
    expect(pct(-0.05, 0)).toBe("-5%");
  });

  it("formats plain dates without timezone drift", () => {
    expect(shortDate("2026-10-09")).toBe("Oct 9");
    expect(shortDate("2026-10-09T23:30:00Z")).toBe("Oct 9");
    expect(shortDate(null)).toBe("-");
    expect(shortDate("garbage")).toBe("garbage");
  });

  it("describes data age", () => {
    const now = new Date("2026-10-16T12:00:00Z");
    expect(ageLabel("2026-10-16T11:40:00Z", now)).toBe("just now");
    expect(ageLabel("2026-10-16T06:00:00Z", now)).toBe("6 h ago");
    expect(ageLabel("2026-10-12T12:00:00Z", now)).toBe("4 d ago");
  });

  it("picks the Filipino text when present, English otherwise", () => {
    const a = answers[0];
    if (!a) throw new Error("fixture");
    expect(text(a, "fil")).toContain("Filipino");
    expect(text({ text: { en: "Only English", fil: null } }, "fil")).toBe("Only English");
  });

  it("filters answers by question", () => {
    expect(byQuestion(answers, "fuel.next_week")).toHaveLength(2);
  });
});
