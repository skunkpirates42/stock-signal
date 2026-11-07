import { readFields, readString } from "../src/lib/parse";
import { expect, test } from "./fixtures";

test("retries a lost queue response as the same run, navigates to its detail, and cancels it", async ({
  page,
}) => {
  const submissions: unknown[] = [];
  const queuedRunIds: string[] = [];
  await page.route("**/api/demo/v1/runs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    submissions.push(route.request().postDataJSON());
    const response = await route.fetch();
    expect(response.ok()).toBe(true);
    const data = readFields(await response.json(), "queue response")("data", readFields);
    const status = data("status", readFields);
    queuedRunIds.push(status("run_id", readString));
    if (submissions.length === 1) {
      await route.fulfill({ status: 502, body: "The accepted queue response was lost" });
      return;
    }
    await route.fulfill({ response });
  });

  await page.goto("/run");
  await expect(page.getByRole("heading", { name: "New run", exact: true })).toBeVisible();
  await expect(page.getByRole("main").getByText(/Synthetic correctness fixture/)).toBeVisible();
  await page.getByRole("button", { name: "Queue historical replay" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toHaveText(
    "The submission response could not be read. Retry to look up the same run.",
  );
  await expect(page).toHaveURL(/\/run$/);
  await page.getByRole("button", { name: "Queue historical replay" }).click();
  await expect(page).toHaveURL(new RegExp(`/runs/${queuedRunIds[0]}$`));
  expect(submissions).toHaveLength(2);
  expect(submissions[1]).toEqual(submissions[0]);
  expect(queuedRunIds[1]).toBe(queuedRunIds[0]);
  await expect(
    page.getByRole("main").getByText("Waiting for the separate local worker to claim this run."),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Exact queued configuration" })).toBeVisible();
  await page.getByRole("button", { name: "Cancel run" }).click();
  await expect(
    page.getByRole("main").getByText("This run was cancelled before a result was published."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Cancel run" })).toHaveCount(0);
  await expect(page.getByRole("main").getByText("Status refreshes every 3 seconds.")).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("main").getByText("No result is published for this job."),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("main").getByText("This run was cancelled before a result was published."),
  ).toBeVisible();
});
