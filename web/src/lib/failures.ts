import { ResponseShapeError } from "@/lib/parse";

export type FailureCategory =
  "transport" | "http" | "timeout" | "aborted" | "schema" | "json" | "unexpected";
export type FailureResource =
  | "operational-status"
  | "market-status"
  | "position-state"
  | "position-prices"
  | "route"
  | "layout"
  | "poll";

export class RequestFailure extends Error {
  constructor(readonly category: FailureCategory) {
    super("The data request failed");
  }
}

export function failureCategory(error: unknown): FailureCategory {
  if (error instanceof RequestFailure) return error.category;
  if (error instanceof ResponseShapeError) return "schema";
  if (error instanceof SyntaxError) return "json";
  if (error instanceof Error && error.name === "TimeoutError") return "timeout";
  if (error instanceof Error && error.name === "AbortError") return "aborted";
  return "unexpected";
}

export function failureReference(error: unknown): string | null {
  if (!(error instanceof Error) || !("digest" in error)) return null;
  return typeof error.digest === "string" && /^[a-zA-Z0-9_-]{1,80}$/.test(error.digest)
    ? error.digest
    : null;
}

export function recordFailure(resource: FailureResource, error: unknown) {
  console.error("web_failure", {
    resource,
    category: failureCategory(error),
    reference: failureReference(error),
  });
}

export function polledResourceName(url: string): FailureResource {
  switch (url) {
    case "/api/operational-status":
      return "operational-status";
    case "/api/market-status":
      return "market-status";
    case "/api/position-state":
      return "position-state";
    case "/api/position-prices":
      return "position-prices";
    default:
      return "poll";
  }
}
