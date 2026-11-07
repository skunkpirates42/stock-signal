import { expect, test } from "@playwright/test";

const pages = [
  { path: "/", title: "Closed-trade net P&L" },
  { path: "/positions", title: "Positions" },
  { path: "/signals", title: "Signals" },
  { path: "/runs", title: "Run history" },
  { path: "/research", title: "Research" },
  { path: "/system", title: "Design system" },
];

for (const { path, title } of pages) {
  test(`${path} renders against the sample API`, async ({ page }) => {
    const browserErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") browserErrors.push(message.text());
    });
    page.on("pageerror", (error) => browserErrors.push(error.message));

    const response = await page.goto(path);
    expect(response?.status()).toBe(200);
    const pageTitle =
      path === "/"
        ? page.locator("main").getByText(title, { exact: true }).filter({ visible: true })
        : page.getByRole("heading", { name: title, level: 1, exact: true });
    await expect(pageTitle).toBeVisible();
    await page.waitForLoadState("networkidle");
    await expect(page.getByRole("heading", { name: "Something went wrong" })).toHaveCount(0);
    expect(browserErrors).toEqual([]);
  });
}
