import { expect, test } from "./fixtures";

test("searches beyond 500 rows and preserves filters on refresh, shared links and history", async ({
  page,
  context,
}) => {
  await page.goto("/signals");
  await expect(page.getByRole("status")).toHaveText(
    "Showing 1–50 of 552 matching signals · 1 WAIT hidden by these filters",
  );
  await page.getByRole("combobox", { name: "Ticker", exact: true }).selectOption("DEEP");
  await page.getByRole("button", { name: "Short", exact: true }).click();
  await page.getByRole("main").getByLabel("From (UTC, inclusive)").fill("2026-06-10");
  await page.getByRole("main").getByLabel("To (UTC, inclusive)").fill("2026-06-10");
  await page.getByRole("slider").fill("0.9");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page.getByRole("status")).toHaveText("Showing 1–1 of 1 matching signals");
  await expect(page).toHaveURL(
    /ticker=DEEP&direction=SHORT&min_confidence=0.9&from=2026-06-10&to=2026-06-10/,
  );
  await expect(page.getByRole("main").locator(".signal-row-ticker")).toHaveText("DEEP");
  const sharedUrl = page.url();

  await page.reload();
  await expect(page.getByRole("combobox", { name: "Ticker", exact: true })).toHaveValue("DEEP");
  await expect(page.getByRole("button", { name: "Short", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByRole("slider")).toHaveValue("0.9");
  await expect(page.getByRole("main").getByLabel("From (UTC, inclusive)")).toHaveValue(
    "2026-06-10",
  );

  const sharedPage = await context.newPage();
  await sharedPage.goto(sharedUrl);
  await expect(sharedPage.getByRole("status")).toHaveText("Showing 1–1 of 1 matching signals");
  await sharedPage.close();

  await page.getByRole("link", { name: "Reset filters", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("of 552 matching signals");
  await page.goBack();
  await expect(page.getByRole("combobox", { name: "Ticker", exact: true })).toHaveValue("DEEP");
  await expect(page.getByRole("status")).toHaveText("Showing 1–1 of 1 matching signals");
  await page.goForward();
  await expect(page.getByRole("combobox", { name: "Ticker", exact: true })).toHaveValue("");
  await expect(page.getByRole("status")).toContainText("of 552 matching signals");
});

test("expands one signal at a time with the keyboard without requesting paid explanations", async ({
  page,
}) => {
  const explanationRequests: string[] = [];
  await page.route("**/signals?**", (route) => {
    const request = route.request();
    if (request.method() === "POST" && request.postData() !== "[]") {
      explanationRequests.push(request.url());
      return route.abort("blockedbyclient");
    }
    return route.fallback();
  });
  await page.goto("/signals?ticker=DEEP&include_wait=true");
  await page.waitForLoadState("networkidle");
  const summaries = page.getByRole("main").getByRole("button", { name: /^DEEP (SHORT|WAIT)/ });
  await expect(summaries).toHaveCount(2);
  await summaries.first().focus();
  await page.keyboard.press("Enter");
  await expect(summaries.first()).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("main").locator(".signal-row-detail")).toHaveCount(1);
  await expect(page.getByRole("heading", { name: /Votes/ })).toBeVisible();
  await expect(page.getByText("Source: provenance not recorded")).toBeVisible();
  await summaries.nth(1).focus();
  await page.keyboard.press("Space");
  await expect(summaries.first()).toHaveAttribute("aria-expanded", "false");
  await expect(summaries.nth(1)).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("main").locator(".signal-row-detail")).toHaveCount(1);
  await page.keyboard.press("Enter");
  await expect(summaries.nth(1)).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByRole("main").locator(".signal-row-detail")).toHaveCount(0);
  expect(explanationRequests).toEqual([]);
});

test("keeps an invalid date range local until corrected", async ({ page }) => {
  await page.goto("/signals?ticker=DEEP");
  await page.getByRole("main").getByLabel("From (UTC, inclusive)").fill("2026-06-11");
  await page.getByRole("main").getByLabel("To (UTC, inclusive)").fill("2026-06-10");
  await expect(page.getByRole("main").getByRole("alert")).toHaveText(
    "From must be on or before To.",
  );
  await expect(page.getByRole("button", { name: "Apply filters" })).toBeDisabled();
  await expect(page).toHaveURL(/\/signals\?ticker=DEEP$/);
  await page.getByRole("main").getByLabel("From (UTC, inclusive)").fill("2026-06-10");
  await expect(page.getByRole("main").getByRole("alert")).toHaveCount(0);
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page).toHaveURL(/from=2026-06-10&to=2026-06-10/);
  await expect(page.getByRole("status")).toHaveText(
    "Showing 1–1 of 1 matching signals · 1 WAIT hidden by these filters",
  );
});

test("paginates complete results and resets the page when filters change", async ({ page }) => {
  await page.goto("/signals?ticker=PAGE");
  await expect(page.getByRole("status")).toHaveText("Showing 1–50 of 551 matching signals");
  await page.getByRole("link", { name: "Next page" }).click();
  await expect(page.getByRole("status")).toHaveText("Showing 51–100 of 551 matching signals");
  await expect(page).toHaveURL(/ticker=PAGE&page=2&snapshot_id=\d+/);
  await page.reload();
  await expect(page.getByRole("status")).toHaveText("Showing 51–100 of 551 matching signals");
  await page.getByRole("link", { name: "Previous page" }).click();
  await expect(page.getByRole("status")).toHaveText("Showing 1–50 of 551 matching signals");
  await page.goto("/signals?ticker=PAGE&page=12");
  await expect(page.getByRole("status")).toHaveText("Showing 551–551 of 551 matching signals");
  await expect(page.getByRole("link", { name: "Next page" })).toHaveCount(0);
  await page.getByRole("combobox", { name: "Ticker", exact: true }).selectOption("DEEP");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page).toHaveURL(/\/signals\?ticker=DEEP$/);
  await expect(page.getByRole("status")).toContainText("Showing 1–1 of 1 matching signals");
});

test("WAIT and source controls preserve complete search semantics", async ({ page }) => {
  await page.goto("/signals?ticker=DEEP");
  await page.getByRole("main").getByLabel("Include WAIT").check();
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page.getByRole("status")).toHaveText("Showing 1–2 of 2 matching signals");
  await expect(page).toHaveURL(/include_wait=true/);
  await page.reload();
  await expect(page.getByRole("main").getByLabel("Include WAIT")).toBeChecked();
  await page.getByRole("button", { name: "Wait", exact: true }).click();
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page.getByRole("status")).toHaveText("Showing 1–1 of 1 matching signals");
  await expect(page.getByRole("main").locator(".signal-row .signal-badge").first()).toHaveText(
    "WAIT",
  );

  await page.goto("/signals?ticker=REPLAY_ONLY");
  await expect(page.getByRole("status")).toHaveText("Showing 0–0 of 0 matching signals");
  await expect(
    page
      .getByRole("main")
      .getByText("No signals match these filters across the complete source scope.", {
        exact: false,
      }),
  ).toBeVisible();
  await page.locator(".rail-scope").getByRole("link", { name: "All", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Showing 1–1 of 1 matching signals");
  await expect(page.getByRole("combobox", { name: "Ticker", exact: true })).toHaveValue(
    "REPLAY_ONLY",
  );
  await page.locator(".rail-scope").getByRole("link", { name: "Live", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Showing 0–0 of 0 matching signals");
});
