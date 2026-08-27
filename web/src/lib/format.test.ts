import { describe, expect, it } from "vitest";
import {
  formatCurrency,
  formatPercent,
  formatPrice,
  formatR,
  formatRatio,
  formatTimestamp,
} from "@/lib/format";

describe("formatCurrency", () => {
  it("signs positive values", () => expect(formatCurrency(51.05)).toBe("+$51.05"));
  it("signs negative values", () => expect(formatCurrency(-31.25)).toBe("-$31.25"));
  it("renders zero unsigned", () => expect(formatCurrency(0)).toBe("$0.00"));
  it("groups thousands", () => expect(formatCurrency(99778.11)).toBe("+$99,778.11"));
  it("renders null as a dash", () => expect(formatCurrency(null)).toBe("—"));
});

describe("formatPrice", () => {
  it("renders positives with no sign prefix", () => expect(formatPrice(51.05)).toBe("$51.05"));
  it("renders zero unsigned", () => expect(formatPrice(0)).toBe("$0.00"));
  it("groups thousands", () => expect(formatPrice(99778.11)).toBe("$99,778.11"));
  it("renders null as a dash", () => expect(formatPrice(null)).toBe("—"));
  it("does not crash on a negative input", () => expect(formatPrice(-31.25)).toBe("$31.25"));
});

describe("formatRatio", () => {
  it("renders a plain decimal with no sign or suffix", () => expect(formatRatio(2)).toBe("2.00"));
  it("does not add a sign prefix beyond the number's own", () =>
    expect(formatRatio(-0.4)).toBe("-0.40"));
  it("renders null as a dash", () => expect(formatRatio(null)).toBe("—"));
});

describe("formatPercent", () => {
  it("converts a fraction", () => expect(formatPercent(0.2)).toBe("20.0%"));
  it("rounds a long fraction", () => expect(formatPercent(0.002698)).toBe("0.3%"));
  it("renders null as a dash", () => expect(formatPercent(null)).toBe("—"));
});

describe("formatR", () => {
  it("signs and suffixes", () => expect(formatR(-0.4)).toBe("-0.40R"));
  it("signs positives", () => expect(formatR(2)).toBe("+2.00R"));
});

describe("formatTimestamp", () => {
  it("handles the space-separated bar_timestamp form", () => {
    expect(formatTimestamp("2026-07-15 19:55:00+00:00")).toBe("2026-07-15 19:55 UTC");
  });
  it("handles the ISO created_at form", () => {
    expect(formatTimestamp("2026-07-15T20:54:00.144301+00:00")).toBe("2026-07-15 20:54 UTC");
  });
  it("passes through the literal start label", () => {
    expect(formatTimestamp("start")).toBe("start");
  });
  it("renders null as a dash", () => expect(formatTimestamp(null)).toBe("—"));
});
