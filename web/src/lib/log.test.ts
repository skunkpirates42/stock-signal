import { afterEach, describe, expect, it, vi } from "vitest";
import { formatEvent, logUpstreamError, logUpstreamStatus } from "@/lib/log";

afterEach(() => vi.restoreAllMocks());

describe("formatEvent", () => {
  it("renders the backend's event key=value shape", () => {
    expect(formatEvent("web_upstream_failed", { path: "/api/market-status", status: 500 })).toBe(
      "web_upstream_failed path=/api/market-status status=500",
    );
  });

  it("quotes values the way app_logging does", () => {
    expect(formatEvent("e", { a: "", b: "two words", c: 'q"x', d: "k=v" })).toBe(
      'e a="" b="two words" c="q\\"x" d="k=v"',
    );
  });
});

describe("upstream failure lines", () => {
  function loggedLine(spy: ReturnType<typeof vi.spyOn>): string {
    expect(spy).toHaveBeenCalledTimes(1);
    return String(spy.mock.calls[0][0]);
  }

  it("writes one stderr line with level, source, path and status", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    logUpstreamStatus("/api/position-state", 503);
    expect(loggedLine(spy)).toMatch(
      /^\d{4}-\d\d-\d\dT\S+Z WARNING web web_upstream_failed path=\/api\/position-state status=503$/,
    );
  });

  it("names a refused connection by its cause code", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const refused = new TypeError("fetch failed", {
      cause: Object.assign(new Error("connect"), { code: "ECONNREFUSED" }),
    });
    logUpstreamError("/api/position-prices", refused);
    expect(loggedLine(spy)).toMatch(
      / path=\/api\/position-prices error=TypeError cause=ECONNREFUSED$/,
    );
  });

  it("names timeouts and malformed JSON by error name only, never the message", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    logUpstreamError("/a", new DOMException("private detail", "TimeoutError"));
    logUpstreamError("/b", new SyntaxError("private detail"));
    logUpstreamError("/c", "thrown string");
    const lines = spy.mock.calls.map((call) => String(call[0]));
    expect(lines[0]).toMatch(/ path=\/a error=TimeoutError$/);
    expect(lines[1]).toMatch(/ path=\/b error=SyntaxError$/);
    expect(lines[2]).toMatch(/ path=\/c error=string$/);
    expect(lines.join("\n")).not.toContain("private detail");
  });
});
