import { fileURLToPath } from "node:url";
import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

const eslint = new ESLint({ cwd: fileURLToPath(new URL("../..", import.meta.url)) });

async function readerViolations(source: string, filePath = "src/lib/validation-fixture.ts") {
  const results = await eslint.lintText(source, { filePath });
  expect(results.flatMap((result) => result.messages).filter((message) => message.fatal)).toEqual(
    [],
  );
  return results
    .flatMap((result) => result.messages)
    .filter((message) => message.ruleId === "responses/require-reader");
}

describe("response reader lint policy", () => {
  it.each([
    "const payload = await response.json(); payload.data.status.run_id;",
    "const payload: unknown = await response.json();",
    "const payload = (await response.json()) as Run;",
    "const payload = response.json() as Promise<Run>;",
    "const payload = await response['json']();",
    "const payload = consume(await response.json());",
    "const payload = readRun(response.json());",
  ])("rejects an unvalidated response body: %s", async (source) => {
    expect(await readerViolations(source)).toHaveLength(1);
  });

  it.each([
    "const payload = readRun(await response.json(), 'run');",
    "const payload = read(await response.json(), path);",
    "const payload = readEnvelope(readRun)(await response.json(), path);",
    "return Response.json(await response.json());",
    "return Response.json({ error: { code: 'invalid_request' } });",
  ])("allows readers and server proxy forwarding: %s", async (source) => {
    expect(await readerViolations(`async function load() { ${source} }`)).toEqual([]);
  });

  it.each([
    "src/lib/runRequests.ts",
    "src/hooks/useData.ts",
    "src/components/Form.tsx",
    "src/app/page.tsx",
  ])("enforces readers at application boundaries in %s", async (filePath) => {
    expect(
      await readerViolations(
        "async function load() { const payload = await response.json(); }",
        filePath,
      ),
    ).toHaveLength(1);
  });
});
