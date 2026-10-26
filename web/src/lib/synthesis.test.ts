import { describe, expect, it } from "vitest";
import { describeSynthesisSource, hasLlmReasoning } from "@/lib/synthesis";

describe("describeSynthesisSource", () => {
  it("names the failed provider without showing its raw error", () => {
    const stored =
      "template (fell back from groq: Error code: 403 - {'error': {'message': 'Access denied.'}})";
    expect(describeSynthesisSource(stored)).toBe("template (groq explanation failed)");
  });

  it("shows plain template and provider sources as stored", () => {
    expect(describeSynthesisSource("template")).toBe("template");
    expect(describeSynthesisSource("groq:qwen/qwen3.6-27b")).toBe("groq:qwen/qwen3.6-27b");
  });

  it("says so when no source was recorded", () => {
    expect(describeSynthesisSource(null)).toBe("provenance not recorded");
  });
});

describe("hasLlmReasoning", () => {
  it("treats a missing or empty source as not yet synthesized", () => {
    expect(hasLlmReasoning(null)).toBe(false);
    expect(hasLlmReasoning("")).toBe(false);
  });

  it("treats plain template text as not yet synthesized", () => {
    expect(hasLlmReasoning("template")).toBe(false);
  });

  it("treats a provider fallback as not yet synthesized, so it stays retryable", () => {
    expect(hasLlmReasoning("template (fell back from groq: api down)")).toBe(false);
  });

  it("recognizes real provider output", () => {
    expect(hasLlmReasoning("anthropic:claude-haiku-4-5")).toBe(true);
    expect(hasLlmReasoning("groq:qwen/qwen3.6-27b")).toBe(true);
  });
});
