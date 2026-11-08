import { expect, test } from "./fixtures";

for (const width of [1280, 320]) {
  test(`scoped research styles survive navigation at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/research");
    await expect(page.getByRole("heading", { name: "Research", exact: true })).toBeVisible();
    const resultLink = page
      .getByRole("main")
      .getByRole("link", { name: /for fixture \/ baseline/ });
    await expect(resultLink).toBeVisible();
    await resultLink.click();
    await expect(
      page.getByRole("heading", { name: "fixture / baseline", exact: true }),
    ).toBeVisible();
    await page.getByText("Reproducibility", { exact: true }).click();
    const configuration = page.getByRole("heading", { name: "Exact saved configuration" });
    await expect(configuration).toBeVisible();
    const configurationGrid = configuration.locator("+ dl");
    await expect(configurationGrid).toHaveCSS("display", "grid");
    await expect(configurationGrid.locator("dt").first()).toHaveCSS("text-transform", "uppercase");
    const artifactsHeading = page.getByRole("heading", { name: "Artifact inventory", exact: true });
    await expect(artifactsHeading).toBeVisible();
    const artifactGroups = artifactsHeading.locator("+ p + div");
    await expect(artifactGroups).toHaveCSS("display", "grid");
    const artifactColumns = await artifactGroups.evaluate(
      (element) => getComputedStyle(element).gridTemplateColumns.split(" ").length,
    );
    expect(artifactColumns).toBe(width <= 700 ? 1 : 2);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: testInfo.outputPath(`research-${width}.png`), fullPage: true });

    await page.getByRole("link", { name: "Design system", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Design system", exact: true })).toBeVisible();
    const swatch = page.getByRole("figure").filter({ hasText: "--ground" });
    await expect(swatch).toHaveCSS("border-radius", "6px");
    await page.getByRole("link", { name: "Research", exact: true }).click();
    await expect(resultLink).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
  });
}
