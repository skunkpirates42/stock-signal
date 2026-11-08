import { describe, expect, it } from "vitest";
import { stylesheetViolations } from "./style-policy";

const tokens = `:root {
  --ink: #ffffff;
  --text-body: 1rem;
  --space: 8px;
  --space-content: calc(var(--space) * 2);
  --radius: 8px;
}`;

function rules(source: string) {
  return stylesheetViolations(source, tokens).map(({ rule }) => rule);
}

describe("CSS-aware token policy", () => {
  it("ignores comments, selector punctuation, quoted strings and URLs", () => {
    expect(
      rules(`
      /* color: red; padding: 8px; */
      @media (min-width: 700px) {
        .card:is(:hover, [data-label="red: white; padding: 8px"]) {
          content: "red; white: #fff {}";
          background-image: url("data:image/svg+xml;utf8,<svg fill='red'>");
          color: var(--ink);
          padding: calc((var(--space) * 2) + var(--space-content));
        }
      }
    `),
    ).toEqual([]);
  });

  it.each([
    "#fff",
    "rebeccapurple",
    "rgb(0 0 0 / 50%)",
    "oklch(50% 0.1 20)",
    "light-dark(white, black)",
    "var(--ink, red)",
  ])("rejects literal color %s, including nested fallbacks", (color) =>
    expect(rules(`.card { color: ${color}; }`)).toContain("Colors must come from tokens.css"),
  );

  it("accepts shared nonliteral color keywords", () => {
    expect(rules(`.card { background: transparent; border-color: currentColor; }`)).toEqual([]);
  });

  it.each([
    "font-size: 14px",
    "font-size: var(--text-missing)",
    "font: 12px serif",
    "padding: 8px",
    "gap: calc(var(--space) + 2px)",
    "margin: var(--unrelated)",
    "border-radius: 8px",
    "border-top-left-radius: 2px",
  ])("rejects off-scale %s", (declaration) => {
    expect(rules(`.card { ${declaration}; }`)).not.toEqual([]);
  });

  it("accepts scale tokens, nested arithmetic, zero, auto and radius shorthands", () => {
    expect(
      rules(`.card {
      font-size: var(--text-body); font: inherit;
      margin-inline: auto; padding: 0 calc(var(--space) * 2);
      gap: var(--space-content); border-radius: var(--radius) 0 / var(--radius);
    }`),
    ).toEqual([]);
  });

  it("limits the negative margin exception to the screen reader clip pattern", () => {
    expect(rules(`.sr-only { margin: -1px; }`)).toEqual([]);
    expect(rules(`.card { margin: -1px; }`)).not.toEqual([]);
    expect(rules(`.sr-only { padding: -1px; }`)).not.toEqual([]);
  });

  it("reports malformed CSS rather than silently skipping declarations", () => {
    expect(() => rules(`.card { color: rgb(; }`)).toThrow();
  });
});
