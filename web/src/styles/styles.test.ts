import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { stylesheetViolations } from "./style-policy";

const STYLES_DIR = fileURLToPath(new URL(".", import.meta.url));
const SOURCE_DIR = fileURLToPath(new URL("..", import.meta.url));
const tokenSource = readFileSync(join(STYLES_DIR, "tokens.css"), "utf8");
const stylesheets = readdirSync(SOURCE_DIR, { recursive: true, withFileTypes: true })
  .filter((entry) => entry.isFile() && entry.name.endsWith(".css"))
  .map((entry) => join(entry.parentPath, entry.name))
  .filter((path) => path !== join(STYLES_DIR, "tokens.css"));

describe("stylesheet token policy", () => {
  it("checks both global and component-scoped stylesheets across src", () => {
    expect(stylesheets.some((path) => path.endsWith(".module.css"))).toBe(true);
    expect(stylesheets.some((path) => path.endsWith("globals.css"))).toBe(true);
  });

  for (const path of stylesheets) {
    it(`uses design tokens in ${relative(SOURCE_DIR, path)}`, () => {
      expect(stylesheetViolations(readFileSync(path, "utf8"), tokenSource)).toEqual([]);
    });
  }
});
