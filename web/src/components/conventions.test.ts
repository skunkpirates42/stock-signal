import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SRC_DIR = fileURLToPath(new URL("..", import.meta.url));

function markupFiles() {
  return readdirSync(SRC_DIR, { recursive: true, encoding: "utf8" })
    .filter((path) => path.endsWith(".tsx"))
    .map((path) => ({ path, source: readFileSync(`${SRC_DIR}/${path}`, "utf8") }));
}

describe("page conventions", () => {
  it("finds markup to check", () => expect(markupFiles().length).toBeGreaterThan(20));

  it.each([
    ["page-head", "components/PageHeader.tsx"],
    ["scope-note", "components/ScopeNote.tsx"],
  ])("builds %s markup only through its component", (className, owner) => {
    const handRolled = markupFiles()
      .filter(({ path, source }) => path !== owner && new RegExp(`className="[^"]*\\b${className}\\b`).test(source))
      .map(({ path }) => path);
    expect(handRolled).toEqual([]);
  });

  it("renders the <main> landmark only through Page", () => {
    const handRolled = markupFiles()
      .filter(({ path, source }) => path !== "components/Page.tsx" && /<main[\s>]/.test(source))
      .map(({ path }) => path);
    expect(handRolled).toEqual([]);
  });
});
