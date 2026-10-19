import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const STYLES_DIR = fileURLToPath(new URL(".", import.meta.url));
const COLOR_LITERAL = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(/;
const SCALE_TOKEN = /^var\(--text-[a-z]+\)$/;

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
    const literals = declarations().filter(({ value }) => COLOR_LITERAL.test(value));
    expect(literals).toEqual([]);
  });

  it("size text only with the type scale", () => {
    const offScale = declarations().filter(({ property, value }) =>
      (property === "font-size" && !SCALE_TOKEN.test(value)) || (property === "font" && value !== "inherit"));
    expect(offScale).toEqual([]);
  });
});
