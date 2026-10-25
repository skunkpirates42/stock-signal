import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const STYLES_DIR = fileURLToPath(new URL(".", import.meta.url));
const COLOR_LITERAL = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(/;
const NAMED_COLOR = /\b(?:white|black|red|green|blue|yellow|orange|purple|pink|gray|grey|silver|navy|teal|aqua|cyan|magenta|lime|maroon|olive)\b/i;
const SCALE_TOKEN = /^var\(--text-[a-z]+\)$/;
const SPACING_PROPERTY = /^(?:padding|margin|gap|row-gap|column-gap)(?:-[a-z-]+)?$/;
const SPACE_TERM = /calc\([^()]*var\(--space\)[^()]*\)|var\(--space\)/g;
const RADIUS_TOKEN = /^var\(--radius(?:-[a-z]+)?\)$/;
// The visually-hidden clip pattern needs a literal -1px margin.
const SR_ONLY_MARGIN = "-1px";

function declarations() {
  return readdirSync(STYLES_DIR)
    .filter((name) => name.endsWith(".css") && name !== "tokens.css")
    .flatMap((name) => readFileSync(`${STYLES_DIR}/${name}`, "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .split(/[;{}]/)
      .map((text) => text.trim())
      .filter((text) => text.includes(":"))
      .map((text) => {
        const [property, ...rest] = text.split(":");
        return { file: name, property: property.trim(), value: rest.join(":").trim() };
      }));
}

describe("stylesheets", () => {
  it("finds declarations to check", () => expect(declarations().length).toBeGreaterThan(100));

  it("take every color from tokens.css", () => {
    const literals = declarations().filter(({ value }) => COLOR_LITERAL.test(value) || NAMED_COLOR.test(value));
    expect(literals).toEqual([]);
  });

  it("size text only with the type scale", () => {
    const offScale = declarations().filter(({ property, value }) =>
      (property === "font-size" && !SCALE_TOKEN.test(value)) || (property === "font" && value !== "inherit"));
    expect(offScale).toEqual([]);
  });

  it("space elements only with the spacing token", () => {
    const offScale = declarations().filter(({ property, value }) => {
      if (!SPACING_PROPERTY.test(property) || value === SR_ONLY_MARGIN) return false;
      const literalParts = value.replace(SPACE_TERM, "").split(/\s+/).filter(Boolean);
      return literalParts.some((part) => part !== "0" && part !== "auto");
    });
    expect(offScale).toEqual([]);
  });

  it("round corners only with radius tokens", () => {
    const offScale = declarations().filter(({ property, value }) =>
      property === "border-radius" && !value.split(/\s+/).every((part) => part === "0" || RADIUS_TOKEN.test(part)));
    expect(offScale).toEqual([]);
  });
});
