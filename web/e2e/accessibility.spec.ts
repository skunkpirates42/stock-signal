import AxeBuilder from "@axe-core/playwright";
import type { Locator, Page, TestInfo } from "@playwright/test";
import { PNG } from "pngjs";
import { expect, test } from "./fixtures";

const routes = [
  "/",
  "/?source=all",
  "/signals",
  "/positions",
  "/run",
  "/runs",
  "/research",
  "/system",
];

async function tabTo(page: Page, target: Locator) {
  for (let index = 0; index < 60; index += 1) {
    await page.keyboard.press("Tab");
    if (await target.evaluate((element) => element === document.activeElement)) return;
  }
  await expect(target).toBeFocused();
}

async function expectFocusRing(target: Locator) {
  await expect(target).toBeFocused();
  const outline = await target.evaluate((element) => {
    const style = getComputedStyle(element);
    return { style: style.outlineStyle, width: parseFloat(style.outlineWidth) };
  });
  expect(outline.style).toBe("solid");
  expect(outline.width).toBeGreaterThanOrEqual(2);
}

for (const path of routes) {
  test(`accessibility scan ${path}`, async ({ page, browser }, testInfo) => {
    testInfo.annotations.push({ type: "browser-version", description: browser.version() });
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    await testInfo.attach("axe-results", {
      body: JSON.stringify(results, null, 2),
      contentType: "application/json",
    });
    expect(results.violations).toEqual([]);
    const tables = page.getByRole("table");
    for (const table of await tables.all()) await expect(table).toHaveAccessibleName(/\S/);
  });
}

test("keyboard reaches skip link, navigation, scope and signal filters with visible focus", async ({
  page,
}) => {
  await page.goto("/");
  const skip = page.getByRole("link", { name: "Skip to content" });
  await page.keyboard.press("Tab");
  await expectFocusRing(skip);
  await expect(skip).toBeInViewport();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();

  await page.goto("/");
  const signals = page
    .getByRole("navigation", { name: "Primary" })
    .getByRole("link", { name: "Signals", exact: true });
  await tabTo(page, signals);
  await expectFocusRing(signals);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/signals$/);
  await expect(signals).toHaveAttribute("aria-current", "page");
  const all = page.locator(".rail-scope").getByRole("link", { name: "All", exact: true });
  await tabTo(page, all);
  await expectFocusRing(all);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/source=all/);
  const ticker = page.getByRole("combobox", { name: "Ticker", exact: true });
  await tabTo(page, ticker);
  await expectFocusRing(ticker);
  const confidence = page.getByRole("slider");
  await tabTo(page, confidence);
  await expectFocusRing(confidence);
  const before = Number(await confidence.inputValue());
  await page.keyboard.press("ArrowRight");
  await expect(confidence).toHaveValue(String(Math.min(1, before + 0.01)));
});

test("chart supports arrow keys and an exact-data disclosure without hover", async ({ page }) => {
  await page.goto("/?source=all");
  const chart = page.getByRole("application", { name: "Equity over time" });
  await tabTo(page, chart);
  await expectFocusRing(chart);
  await page.keyboard.press("ArrowRight");
  const tooltip = page.locator(".recharts-tooltip-wrapper");
  await expect(tooltip).toBeVisible();
  const firstValue = await tooltip.textContent();
  await page.keyboard.press("ArrowRight");
  await expect(tooltip).not.toHaveText(firstValue ?? "");
  const summary = page.locator(".equity-data summary");
  await tabTo(page, summary);
  await expectFocusRing(summary);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("table", { name: "Equity data", exact: true })).toBeVisible();
  const dataRows = page
    .getByRole("table", { name: "Equity data", exact: true })
    .locator("tbody tr");
  expect(await dataRows.count()).toBeGreaterThanOrEqual(2);
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.keyboard.press("Space");
  await expect(page.getByRole("table", { name: "Equity data", exact: true })).toBeHidden();
});

for (const preference of ["reduce", "no-preference"] as const) {
  test(`Recharts JavaScript reveal honors motion preference: ${preference}`, async ({
    page,
  }, testInfo) => {
    await page.emulateMedia({ reducedMotion: preference });
    await page.addInitScript(() => {
      let widthChanges = 0;
      Object.defineProperty(window, "chartWidthChanges", { get: () => widthChanges });
      new MutationObserver((records) => {
        for (const record of records) {
          if (
            record.target instanceof SVGElement &&
            record.target.matches(".recharts-area clipPath rect")
          )
            widthChanges += 1;
        }
      }).observe(document, { subtree: true, attributes: true, attributeFilter: ["width"] });
    });
    await page.goto("/?source=all");
    await expect(page.locator(".recharts-area-curve")).toHaveAttribute("d", /^M.+/);
    if (preference === "no-preference") {
      await expect
        .poll(() => page.evaluate(() => Reflect.get(window, "chartWidthChanges")))
        .toBeGreaterThan(2);
    }
    await page.waitForTimeout(1700);
    const widthChanges = await page.evaluate(() => Reflect.get(window, "chartWidthChanges"));
    await testInfo.attach("recharts-motion", {
      body: JSON.stringify({ preference, widthChanges }),
      contentType: "application/json",
    });
    if (preference === "reduce") expect(widthChanges).toBe(0);
  });
}

test("320px layout keeps navigation, long figures and table scrolling reachable", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 320, height: 800 });
  for (const path of [
    "/?source=all",
    "/positions",
    "/signals?ticker=DEEP&include_wait=true",
    "/run",
    "/research",
    "/system",
  ]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    for (const link of await page
      .getByRole("navigation", { name: "Primary" })
      .getByRole("link")
      .all()) {
      const box = await link.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(321);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      320,
    );
    if (path === "/?source=all") {
      await page.locator(".hero-value").evaluate((element) => {
        element.textContent = "−$123,456,789,012.34";
      });
      await page
        .locator(".stat-tile-value")
        .first()
        .evaluate((element) => {
          element.textContent = "−$123,456,789.99";
        });
      expect(
        await page
          .locator(".hero-value")
          .evaluate((element) => element.scrollWidth <= element.clientWidth),
      ).toBe(true);
    }
    if (path.startsWith("/signals")) {
      const signal = page.getByRole("main").getByRole("button", { name: /^DEEP SHORT/ });
      await tabTo(page, signal);
      await expectFocusRing(signal);
      await expect(signal).toHaveCSS("outline-offset", "-3px");
      await page.keyboard.press("Enter");
      await expect(page.getByText("No indicator votes recorded for this signal.")).toBeVisible();
    }
    await testInfo.attach(`narrow-${path.replace(/\W/g, "_")}`, {
      body: await page.screenshot({ fullPage: true }),
      contentType: "image/png",
    });
  }
  const table = page.getByRole("table", { name: "Sample trades", exact: true });
  await table
    .locator("tbody td")
    .first()
    .evaluate((element) => {
      element.textContent = "LONG_ACCOUNT_IDENTIFIER_1234567890123456789012345678901234567890";
    });
  const scrollArea = page.getByRole("region", {
    name: "Sample trades table scroll area",
    exact: true,
  });
  await tabTo(page, scrollArea);
  await expectFocusRing(scrollArea);
  expect(await scrollArea.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(
    true,
  );
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => scrollArea.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
});

function luminance(channels: number[]) {
  const [red, green, blue] = channels.map((channel) => {
    const value = channel / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return red * 0.2126 + green * 0.7152 + blue * 0.0722;
}

async function renderedContrast(target: Locator, testInfo: TestInfo, surface: string) {
  await target.scrollIntoViewIfNeeded();
  const foreground = await target.evaluate((element) => getComputedStyle(element).color);
  const foregroundChannels = foreground
    .match(/[\d.]+/g)!
    .slice(0, 3)
    .map(Number);
  await target.evaluate((element) => element.setAttribute("data-contrast-probe", ""));
  const backgroundImage = await target.screenshot({
    style:
      "[data-contrast-probe], [data-contrast-probe] * { color: transparent !important; text-decoration: none !important; text-shadow: none !important; transition: none !important; }",
  });
  const background = PNG.sync.read(backgroundImage);
  await testInfo.attach(`contrast-${surface}`, { body: backgroundImage, contentType: "image/png" });
  await target.evaluate((element) => element.removeAttribute("data-contrast-probe"));
  const ratios = [0.25, 0.5, 0.75].flatMap((vertical) =>
    [0.25, 0.5, 0.75].map((horizontal) => {
      const offset =
        (Math.floor(background.height * vertical) * background.width +
          Math.floor(background.width * horizontal)) *
        4;
      const backgroundLuminance = luminance([...background.data.subarray(offset, offset + 3)]);
      const foregroundLuminance = luminance(foregroundChannels);
      return (
        (Math.max(foregroundLuminance, backgroundLuminance) + 0.05) /
        (Math.min(foregroundLuminance, backgroundLuminance) + 0.05)
      );
    }),
  );
  return { foreground, minimumRatio: Math.min(...ratios) };
}

test("small text meets AA on rendered translucent, gradient and active surfaces", async ({
  page,
}, testInfo) => {
  const samples: { surface: string; foreground: string; minimumRatio: number }[] = [];
  for (const [path, selectors] of [
    [
      "/?source=all",
      [
        ".rail-link-active",
        ".stat-tile-label",
        ".card-note",
        ".data-table thead th",
        ".tone-positive",
      ],
    ],
    [
      "/signals?ticker=DEEP",
      [".signal-row-timestamp", ".filter-field .micro", ".segmented-option-active"],
    ],
  ] as const) {
    await page.goto(path);
    for (const selector of selectors) {
      samples.push({
        surface: selector,
        ...(await renderedContrast(
          page.locator(selector).filter({ visible: true }).first(),
          testInfo,
          selector,
        )),
      });
    }
  }
  await testInfo.attach("rendered-contrast", {
    body: JSON.stringify(samples, null, 2),
    contentType: "application/json",
  });
  for (const sample of samples)
    expect(sample.minimumRatio, sample.surface).toBeGreaterThanOrEqual(4.5);
});
