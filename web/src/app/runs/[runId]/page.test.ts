import { describe, expect, it, vi } from "vitest";
import { Children, isValidElement, type ReactNode } from "react";

const available = (value: string) => ({ availability: "available" as const, value, reason: null, detail: null });
const unavailable = (detail: string) => ({ availability: "unavailable" as const, value: null, reason: "not_recorded" as const, detail });

const validDetail = {
  result: {
    record_type: "result", id: "result-uuid", run_id: "saved-run-uuid", variant: "baseline",
    window: { name: "review", role: "holdout", start: "2026-01-01T00:00:00Z", end_exclusive: "2026-02-01T00:00:00Z" },
    provenance: { source: "backtest", execution: "local_simulation", historical: true, retrospective: true, synthetic: false, evaluation: "retrospective", holdout_status: unavailable("No prospective registration."), label_evidence: ["Saved protocol"] },
    accounting: { version: unavailable("No policy version."), mode: "recorded_costs_only", coverage: "incomplete", unresolved: ["Borrow is not modeled."] },
    metrics: {
      realized_net_pnl: { observation: { availability: "available", value: 12.5, reason: null, detail: "saved" }, unit: "USD", basis: "Saved closed trades", source_pointer: "/comparison" },
      marked_net_pnl: { observation: { availability: "available", value: 9.5, reason: null, detail: "saved" }, unit: "USD", basis: "Saved marks", source_pointer: "/marked_review" },
      fees: { observation: { availability: "unavailable", value: null, reason: "not_recorded", detail: "Separate fees were not saved." }, unit: "USD", basis: "No fee total", source_pointer: null },
      borrow_cost: { observation: { availability: "unavailable", value: null, reason: "not_modeled", detail: "Borrow is not modeled." }, unit: "USD", basis: "No borrow amount", source_pointer: null },
      dividend_cashflow: { observation: { availability: "unavailable", value: null, reason: "not_modeled", detail: "Dividends are not modeled." }, unit: "USD", basis: "No dividend amount", source_pointer: null },
      spread_cost: { observation: { availability: "unavailable", value: null, reason: "not_recorded", detail: "Spread total was not saved." }, unit: "USD", basis: "No spread total", source_pointer: null },
      slippage_cost: { observation: { availability: "unavailable", value: null, reason: "not_recorded", detail: "Slippage total was not saved." }, unit: "USD", basis: "No slippage total", source_pointer: null },
    },
    by_regime: unavailable("No regimes."), limitations: ["Marks exclude hypothetical exit costs."], artifact_ids: ["artifact-uuid"],
  },
  run: {
    record_type: "normalized_run", id: "saved-run-uuid", strategy_id: "stock-signal", strategy_version: unavailable("Legacy strategy."), variant: "baseline", dataset_id: "dataset-uuid", dataset_sha256: available("dataset-hash"), selected_data_sha256: available("selected-hash"),
    window: { name: "review", role: "holdout", start: "2026-01-01T00:00:00Z", end_exclusive: "2026-02-01T00:00:00Z" }, observed_bounds: { first_bar: available("2026-01-01T14:30:00Z"), last_bar: unavailable("No final mark.") }, symbols: ["AAA"], feed: available("iex"), cost_policy: { id: "saved", spread_bps: 2, slippage_bps_per_fill: 1, fee_per_share_per_fill: 0, evidence: "saved source" }, accounting: { version: unavailable("No policy version."), mode: "recorded_costs_only", coverage: "incomplete", unresolved: ["Borrow is not modeled."] }, fill_policy: available("next close"), session_policy: available("regular"), code: { revision: unavailable("No revision."), source_sha256: unavailable("No source hash."), working_diff_sha256: unavailable("No diff hash.") }, provenance: { source: "backtest", execution: "local_simulation", historical: true, retrospective: true, synthetic: false, evaluation: "retrospective", holdout_status: unavailable("No prospective registration."), label_evidence: ["Saved protocol"] },
  },
  artifacts: [{ record_type: "artifact", id: "artifact-uuid", result_id: "result-uuid", kind: "metrics", sha256: "a".repeat(64), mime_type: "application/json", byte_size: 42 }],
  status: { origin: "saved_artifact", state: "completed", run_id: "saved-run-uuid" },
};

vi.mock("@/lib/demo", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/demo")>();
  return { ...actual, getSavedResult: vi.fn(async () => ({ data: validDetail, warnings: ["Saved result only."] })) };
});

import Page from "./page";
import { getSavedResult } from "@/lib/demo";

function textOf(node: unknown): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (!isValidElement<{ children?: unknown }>(node)) return "";
  return Children.toArray(node.props.children as ReactNode).map(textOf).join(" ");
}

describe("saved result page", () => {
  it("renders supplied saved metrics, configuration, and result-scoped artifacts", async () => {
    const page = await Page({ params: Promise.resolve({ runId: "result-uuid" }) });
    const text = textOf(page);
    expect(text).toContain("+$12.50");
    expect(text).toContain("Saved closed trades");
    expect(text).toContain("dataset-hash");
    expect(text).toContain("saved-run-uuid");
    expect(text).toContain("Marks exclude hypothetical exit costs.");
    expect(text).toContain("metrics");
    expect(text).toContain("borrow cost");
    expect(text).toContain("inclusive");
  });

  it("keeps incomplete values unavailable instead of treating them as zero", async () => {
    const page = await Page({ params: Promise.resolve({ runId: "result-uuid" }) });
    const text = textOf(page);
    expect(text).toContain("Unavailable: Separate fees were not saved.");
    expect(text).toContain("Unresolved accounting:");
    expect(text).toContain("Borrow is not modeled.");
    expect(text).not.toContain("+$0.00");
  });

  it("uses the route-local missing-result UI for an A3 404", async () => {
    vi.mocked(getSavedResult).mockRejectedValueOnce(Object.assign(new Error("missing"), { name: "DemoNotFound" }));
    await expect(Page({ params: Promise.resolve({ runId: "result-uuid" }) })).rejects.toMatchObject({ digest: "NEXT_HTTP_ERROR_FALLBACK;404" });
  });
});
