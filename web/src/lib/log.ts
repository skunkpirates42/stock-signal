type EventFields = Record<string, string | number>;

const UPSTREAM_FAILED = "web_upstream_failed";

export function formatEvent(event: string, fields: EventFields): string {
  const pairs = Object.entries(fields).map(([key, value]) => `${key}=${formatValue(value)}`);
  return [event, ...pairs].join(" ");
}

function formatValue(value: string | number): string {
  const text = String(value);
  return text === "" || /[\s"=]/.test(text) ? JSON.stringify(text) : text;
}

function logWarning(event: string, fields: EventFields): void {
  console.error(`${new Date().toISOString()} WARNING web ${formatEvent(event, fields)}`);
}

export function logUpstreamStatus(path: string, status: number): void {
  logWarning(UPSTREAM_FAILED, { path, status });
}

export function logUpstreamError(path: string, error: unknown): void {
  logWarning(UPSTREAM_FAILED, { path, ...describeError(error) });
}

function describeError(error: unknown): EventFields {
  if (!(error instanceof Error)) return { error: typeof error };
  // Node's fetch reports a refused or reset connection as TypeError("fetch failed");
  // only the cause code says whether Flask was down.
  const causeCode = (error.cause as { code?: unknown } | undefined)?.code;
  return typeof causeCode === "string"
    ? { error: error.name, cause: causeCode }
    : { error: error.name };
}
