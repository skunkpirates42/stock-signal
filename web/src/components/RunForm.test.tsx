// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ReplayCatalog } from "@/lib/jobs/contracts";
import { RUN_REQUEST_TIMEOUT_MS, type ReplayChoices } from "@/lib/runRequests";
import RunForm from "./RunForm";

const navigation = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => navigation }));

const catalog: ReplayCatalog = {
  strategy: { id: "stock-signal", label: "Fixed strategy", editable_fields: [] },
  datasets: [
    {
      id: "fixture",
      label: "Synthetic fixture",
      content_sha256: "a".repeat(64),
      feed: "synthetic",
      synthetic: true,
      available: true,
      windows: [{ id: "fixture-day-2", start: "2026-06-10", end_exclusive: "2026-06-11" }],
      cost_profile_ids: ["base-v2", "adverse-v2"],
    },
  ],
  cost_profiles: ["base-v2", "adverse-v2"].map((id) => ({
    id,
    label: id,
    spread_bps: 2,
    slippage_bps_per_fill: 1,
    fee_per_share_per_fill: 0,
    evidence: "Bounded synthetic scenario",
  })),
};

const fetchResponse = vi.fn<typeof fetch>();
const RUN_ID = "123e4567-e89b-12d3-a456-426614174000";

beforeEach(() => {
  fetchResponse.mockReset();
  navigation.push.mockReset();
  vi.stubGlobal("fetch", fetchResponse);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

async function submit() {
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: "Queue historical replay" })),
  );
}

function submittedChoices(index: number): ReplayChoices {
  const body = fetchResponse.mock.calls[index][1]?.body;
  expect(typeof body).toBe("string");
  return JSON.parse(String(body));
}

it("disables pending submissions and retries unreadable responses with the same idempotency key", async () => {
  let finishRequest: ((response: Response) => void) | undefined;
  fetchResponse.mockImplementationOnce(() => new Promise((resolve) => (finishRequest = resolve)));
  render(<RunForm catalog={catalog} />);
  await submit();
  expect(screen.getByRole<HTMLButtonElement>("button", { name: "Submitting…" }).disabled).toBe(
    true,
  );
  expect(screen.getByLabelText<HTMLSelectElement>("Cost scenario").disabled).toBe(true);
  fireEvent.submit(screen.getByRole("button", { name: "Submitting…" }).closest("form")!);
  expect(fetchResponse).toHaveBeenCalledTimes(1);
  await act(async () => finishRequest?.(new Response("response lost", { status: 502 })));
  expect(screen.getByRole("alert").textContent).toContain("Retry to look up the same run");
  expect(navigation.push).not.toHaveBeenCalled();

  fetchResponse.mockResolvedValueOnce(Response.json({ data: { status: { run_id: RUN_ID } } }));
  await submit();
  expect(submittedChoices(1)).toEqual(submittedChoices(0));
  expect(navigation.push).toHaveBeenCalledExactlyOnceWith(`/runs/${RUN_ID}`);
});

it("recovers controls after a timeout and looks up the accepted run with the same key", async () => {
  vi.useFakeTimers();
  let finishOriginalRequest: ((response: Response) => void) | undefined;
  fetchResponse.mockImplementationOnce(
    () => new Promise((resolve) => (finishOriginalRequest = resolve)),
  );
  render(<RunForm catalog={catalog} />);
  await submit();
  await act(async () => vi.advanceTimersByTimeAsync(RUN_REQUEST_TIMEOUT_MS));
  expect(screen.getByRole("alert").textContent).toContain("run may still have been queued");
  expect(
    screen.getByRole<HTMLButtonElement>("button", { name: "Queue historical replay" }).disabled,
  ).toBe(false);
  expect(screen.getByLabelText<HTMLSelectElement>("Cost scenario").disabled).toBe(false);
  expect(navigation.push).not.toHaveBeenCalled();

  fetchResponse.mockResolvedValueOnce(
    Response.json({ data: { status: { run_id: RUN_ID } } }, { status: 202 }),
  );
  await submit();
  expect(submittedChoices(1)).toEqual(submittedChoices(0));
  expect(navigation.push).toHaveBeenCalledExactlyOnceWith(`/runs/${RUN_ID}`);

  await act(async () =>
    finishOriginalRequest?.(Response.json({ data: { status: { run_id: RUN_ID } } })),
  );
  expect(navigation.push).toHaveBeenCalledTimes(1);
  expect(vi.getTimerCount()).toBe(0);
});

it("creates a new key when choices change and when the server rejects a conflicting key", async () => {
  fetchResponse.mockRejectedValueOnce(new Error("offline"));
  render(<RunForm catalog={catalog} />);
  await submit();
  fireEvent.change(screen.getByLabelText("Cost scenario"), { target: { value: "adverse-v2" } });
  expect(screen.queryByRole("alert")).toBeNull();
  fetchResponse.mockResolvedValueOnce(
    Response.json({ error: { code: "idempotency_conflict" } }, { status: 409 }),
  );
  await submit();
  expect(submittedChoices(1)).toMatchObject({ cost_profile_id: "adverse-v2" });
  expect(submittedChoices(1).idempotency_key).not.toBe(submittedChoices(0).idempotency_key);
  expect(screen.getByRole("alert").textContent).toContain("submission key was already used");
  fetchResponse.mockResolvedValueOnce(Response.json({ data: { status: { run_id: RUN_ID } } }));
  await submit();
  expect(submittedChoices(2).idempotency_key).not.toBe(submittedChoices(1).idempotency_key);
  expect(navigation.push).toHaveBeenCalledWith(`/runs/${RUN_ID}`);
});

it("prevents submission when no approved local dataset is available", () => {
  render(<RunForm catalog={{ ...catalog, datasets: [] }} />);
  expect(screen.getByText(/No approved dataset is available/)).toBeDefined();
  expect(
    screen.getByRole<HTMLButtonElement>("button", { name: "Queue historical replay" }).disabled,
  ).toBe(true);
  expect(fetchResponse).not.toHaveBeenCalled();
});
