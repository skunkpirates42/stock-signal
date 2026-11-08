import { chromium } from "@playwright/test";
import { resolve } from "node:path";
import { expect, test } from "./fixtures";

const extensionPath = resolve(__dirname, "zoom-extension");

test("browser zoom at 200% and 400% reflows navigation, forms and long values", async ({}, testInfo) => {
  const context = await chromium.launchPersistentContext("", {
    channel: "chromium",
    args: [
      `--disable-extensions-except=${extensionPath}`,
      `--load-extension=${extensionPath}`,
      "--window-size=1280,960",
    ],
    viewport: null,
    deviceScaleFactor: undefined,
    serviceWorkers: "allow",
  });
  try {
    const externalRequests: string[] = [];
    await context.route("**/*", (route) => {
      const url = new URL(route.request().url());
      if (["127.0.0.1", "localhost"].includes(url.hostname)) return route.continue();
      externalRequests.push(`${url.origin}${url.pathname}`);
      return route.abort();
    });
    const worker = context.serviceWorkers()[0] ?? (await context.waitForEvent("serviceworker"));
    const page = context.pages()[0];
    await page.goto("http://127.0.0.1:13000/?source=all");
    const browserSession = await context.newCDPSession(page);
    const zoomMeasurements: { factor: number; width: number; pixelRatio: number }[] = [];
    const initial = await page.evaluate(() => ({
      width: innerWidth,
      pixelRatio: devicePixelRatio,
    }));
    for (const factor of [2, 4]) {
      const actualZoom = await worker.evaluate(`(async () => {
        const tabs = await chrome.tabs.query({url: 'http://127.0.0.1:13000/*'});
        await chrome.tabs.setZoom(tabs[0].id, ${factor});
        return chrome.tabs.getZoom(tabs[0].id);
      })()`);
      expect(actualZoom).toBeCloseTo(factor, 5);
      await expect
        .poll(() => page.evaluate(() => innerWidth))
        .toBe(Math.round(initial.width / factor));
      expect(await page.evaluate(() => devicePixelRatio)).toBeCloseTo(
        initial.pixelRatio * factor,
        1,
      );
      zoomMeasurements.push({
        factor,
        ...(await page.evaluate(() => ({ width: innerWidth, pixelRatio: devicePixelRatio }))),
      });
      for (const path of ["/?source=all", "/run", "/signals?ticker=DEEP", "/positions"]) {
        await page.goto(`http://127.0.0.1:13000${path}`);
        await page.waitForLoadState("networkidle");
        if (path === "/?source=all") {
          await page.locator(".hero-value").evaluate((element) => {
            element.textContent = "−$123,456,789,012.34";
          });
          expect(
            await page
              .locator(".hero-value")
              .evaluate((element) => element.scrollWidth <= element.clientWidth),
          ).toBe(true);
        }
        const overflowingControls = await page
          .locator(".rail a, input, select, .signal-row-summary")
          .evaluateAll((elements) =>
            elements
              .filter((element) => {
                const bounds = element.getBoundingClientRect();
                return bounds.left < 0 || bounds.right > innerWidth + 1;
              })
              .map((element) => element.textContent || element.getAttribute("name")),
          );
        expect(overflowingControls).toEqual([]);
        await testInfo.attach(`zoom-${factor}-${path.replace(/\W/g, "_")}`, {
          body: Buffer.from(
            (await browserSession.send("Page.captureScreenshot", { format: "png" })).data,
            "base64",
          ),
          contentType: "image/png",
        });
      }
    }
    await testInfo.attach("browser-zoom-measurements", {
      body: JSON.stringify({ initial, zoomMeasurements }),
      contentType: "application/json",
    });
    expect(externalRequests).toEqual([]);
  } finally {
    await context.close();
  }
});
