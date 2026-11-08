import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { parse, walk, generate } from "css-tree";
import { describe, expect, it } from "vitest";

const tokenSource = readFileSync(fileURLToPath(new URL("./tokens.css", import.meta.url)), "utf8");

const TEXT_TOKENS = ["--ink", "--muted", "--faint", "--accent", "--caution", "--win", "--loss"];
const WCAG_AA_BODY_TEXT = 4.5;

function tokenColor(name: string) {
  let hex: string | undefined;
  walk(parse(tokenSource, { parseCustomProperty: true }), {
    visit: "Declaration",
    enter(node) {
      if (node.property === name) hex = generate(node.value).slice(1);
    },
  });
  if (!hex || hex.length !== 6 || Number.isNaN(Number(`0x${hex}`))) {
    throw new Error(`${name} is not a six-digit hex color in tokens.css`);
  }
  return hex;
}

function relativeLuminance(hex: string) {
  const [red, green, blue] = [0, 2, 4].map((offset) => {
    const channel = parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

function contrastRatio(foreground: string, background: string) {
  const [lighter, darker] = [relativeLuminance(foreground), relativeLuminance(background)].sort(
    (a, b) => b - a,
  );
  return (lighter + 0.05) / (darker + 0.05);
}

describe("color tokens", () => {
  it("meet WCAG AA contrast for body text against the page ground", () => {
    const ground = tokenColor("--ground");
    const failing = TEXT_TOKENS.map((token) => ({
      token,
      ratio: Number(contrastRatio(tokenColor(token), ground).toFixed(2)),
    })).filter(({ ratio }) => ratio < WCAG_AA_BODY_TEXT);
    expect(failing).toEqual([]);
  });
});
