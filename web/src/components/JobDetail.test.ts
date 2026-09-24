import { describe, expect, it } from "vitest";
import { Children, isValidElement, type ReactNode } from "react";
import JobDetail from "./JobDetail";
import type { JobDetail as Detail } from "@/lib/jobs";

const available = <T,>(value: T) => ({ availability: "available" as const, value, reason: null, detail: null });
const unavailable = (detail: string) => ({ availability: "unavailable" as const, value: null, reason: "not_recorded" as const, detail });
const RUN_ID = "123e4567-e89b-12d3-a456-426614174000";

function content(node: unknown): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (!isValidElement<{ children?: unknown; href?: string }>(node)) return "";
  return [node.props.href, ...Children.toArray(node.props.children as ReactNode)].map(content).join(" ");
}

function detail(state: "failed" | "completed"): Detail {
  return {
    run: { id: RUN_ID, strategy_id: "stock-signal", strategy_version: available("v1"), dataset_id: "fixture",
      dataset_sha256: available("digest"), selected_data_sha256: available("selected"),
      variant: "baseline", window: { name: "fixture-day-2", role: "evaluation", start: "2026-09-24T12:00:00Z", end_exclusive: "2026-09-24T13:00:00Z" },
      provenance: { synthetic: true, retrospective: false, evaluation: "synthetic_correctness" }, feed: available("synthetic"),
      symbols: ["AAA"], observed_bounds: { first_bar: available("2026-09-24T11:00:00Z") },
      fill_policy: available("delayed bar"), session_policy: available("regular"),
      cost_policy: { id: "base-v2", spread_bps: 2, slippage_bps_per_fill: 1, fee_per_share_per_fill: 0, evidence: "Scenario" },
      accounting: { mode: "cashflow_accounted", coverage: "incomplete", version: available("2"), unresolved: ["borrow_cost"] },
      code: { revision: unavailable("No revision"), source_sha256: available("source"), working_diff_sha256: available("dirty-digest") },
    } as unknown as Detail["run"],
    status: { state, run_id: RUN_ID, phase: unavailable("No phase"), attempt: available(2),
      created_at: available("2026-09-24T12:00:00Z"), started_at: unavailable("Not started"),
      heartbeat_at: unavailable("No heartbeat"), ended_at: available("2026-09-24T12:01:00Z"),
      failure: state === "failed" ? { code: "worker_lost", summary: "The worker stopped reporting before the run finished.", at: "2026-09-24T12:01:00Z", retryable: false } : unavailable("No failure"),
    } as unknown as Detail["status"],
    result: state === "completed" ? { id: "result-id", metrics: {
      realized_net_pnl: { observation: available(12), unit: "USD", basis: "Saved Python result" },
      marked_net_per_session: { observation: available(3), unit: "USD/session", basis: "Saved marked sessions" },
    },
      accounting: { coverage: "incomplete" }, limitations: ["Synthetic correctness only"] } as unknown as Detail["result"] : null,
    artifacts: state === "completed" ? [{ id: "artifact-id", kind: "report", mime_type: "text/plain", byte_size: 42, sha256: "a".repeat(64) }] as unknown as Detail["artifacts"] : [],
  };
}

describe("historical job detail", () => {
  it("shows a lost worker failure and no unpublished result", () => {
    const text = content(JobDetail({ detail: detail("failed"), warnings: [] }));
    expect(text).toContain("worker_lost: The worker stopped reporting");
    expect(text).toContain("No result is published");
    expect(text).not.toContain("/artifacts/");
  });

  it("shows the saved Python metric basis and published artifact link", () => {
    const text = content(JobDetail({ detail: detail("completed"), warnings: [] }));
    expect(text).toContain("Saved Python result");
    expect(text).toContain("+$3.00/session");
    expect(text).toContain("dirty-digest");
    expect(text).toContain("delayed bar");
    expect(text).toContain("Synthetic correctness only");
    expect(text).toContain(`/api/demo/v1/runs/${RUN_ID}/artifacts/artifact-id`);
  });
});
