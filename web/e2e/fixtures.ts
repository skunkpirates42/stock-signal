import { expect, test as browserTest } from "@playwright/test";

export const test = browserTest.extend<{ localRequestsOnly: void }>({
  localRequestsOnly: [
    async ({ context }, use) => {
      const externalRequests: string[] = [];
      await context.route("**/*", (route) => {
        const url = new URL(route.request().url());
        if (["127.0.0.1", "localhost"].includes(url.hostname)) return route.fallback();
        externalRequests.push(`${url.origin}${url.pathname}`);
        return route.abort("blockedbyclient");
      });
      await use();
      expect(externalRequests, "Browser flows must use only the local fixture servers").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };
