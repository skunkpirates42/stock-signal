import { describe, expect, it } from "vitest";
import { hasLlmReasoning } from "@/lib/synthesis";

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
