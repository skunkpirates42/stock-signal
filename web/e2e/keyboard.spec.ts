import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./fixtures";

test("opens metric definitions with keyboard focus and dismisses with Escape, blur and outside pointer", async ({
  page,
}, testInfo) => {
  await page.goto("/");
  const term = page.getByRole("button", { name: "Profit factor", exact: true });
  await expect(term).toHaveAttribute("aria-expanded", "false");
  for (let tab = 0; tab < 40; tab += 1) {
    await page.keyboard.press("Tab");
    if (await term.evaluate((button) => button === document.activeElement)) break;
  }
  await expect(term).toBeFocused();
  await expect(term).toHaveAttribute("aria-expanded", "true");
  const panelId = await term.getAttribute("aria-controls");
  const panel = page.locator(`[id="${panelId}"]`);
  await expect(panel).toBeVisible();
  await expect(panel).toContainText(
    "total $ won by winning trades ÷ total $ lost by losing trades",
  );
  await page.evaluate(() => window.scrollBy(0, 32));
  await expect(panel).toBeVisible();
  const panelBounds = await panel.boundingBox();
  expect(panelBounds!.x).toBeGreaterThanOrEqual(16);
  expect(panelBounds!.x + panelBounds!.width).toBeLessThanOrEqual(page.viewportSize()!.width - 15);
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await testInfo.attach("focused-metric-definition", {
    body: await page.screenshot(),
    contentType: "image/png",
  });
  await page.keyboard.press("Escape");
  await expect(term).toHaveAttribute("aria-expanded", "false");
  await expect(panel).toBeHidden();
  await expect(term).toBeFocused();

  await page.keyboard.press("Enter");
  await expect(panel).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(panel).toBeHidden();
  await page.keyboard.press("Space");
  await expect(panel).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(panel).toBeHidden();
  await term.focus();
  await expect(panel).toBeVisible();
  await page.locator("main").getByText("Closed-trade net P&L", { exact: true }).click();
  await expect(panel).toBeHidden();
});

test("toggles native account disclosures with Enter and Space", async ({ page }) => {
  await page.goto("/positions");
  const account = page.getByLabel("Paper account status");
  const disclosure = account.locator("details");
  const summary = account.locator("summary");
  await expect(disclosure).not.toHaveAttribute("open");
  await summary.focus();
  await page.keyboard.press("Enter");
  await expect(disclosure).toHaveAttribute("open", "");
  await expect(account.getByText(/Endpoint fetched:/)).toBeVisible();
  await page.keyboard.press("Space");
  await expect(disclosure).not.toHaveAttribute("open");
  await expect(account.getByText(/Endpoint fetched:/)).toBeHidden();
  await expect(summary).toBeFocused();
});
