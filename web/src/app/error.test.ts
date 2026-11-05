import { describe, expect, it, vi } from "vitest";
import { Children, isValidElement, type ReactNode } from "react";
import ErrorPage from "./error";

function textOf(node: unknown): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (!isValidElement<{ children?: ReactNode }>(node)) return "";
  return Children.toArray(node.props.children)
    .map((child) => textOf(child))
    .join("");
}

function findButton(node: unknown): { onClick: () => void } | undefined {
  if (!isValidElement<{ onClick?: () => void; children?: ReactNode }>(node)) return undefined;
  if (node.type === "button" && node.props.onClick) return { onClick: node.props.onClick };
  for (const child of Children.toArray(node.props.children)) {
    const found = findButton(child);
    if (found) return found;
  }
  return undefined;
}

describe("route error page", () => {
  it("points at the Flask API and its URL setting without naming a fixed port", () => {
    const text = textOf(ErrorPage({ error: new Error("fetch failed"), retry: () => {} }));
    expect(text).toContain("Flask API");
    expect(text).toContain("FLASK_API_URL");
    expect(text).not.toMatch(/port \d+/);
  });

  it("shows the error message and, when present, the digest for matching server logs", () => {
    const error = Object.assign(new Error("fetch failed"), { digest: "abc123" });
    const text = textOf(ErrorPage({ error, retry: () => {} }));
    expect(text).toContain("fetch failed");
    expect(text).toContain("abc123");
  });

  it("retries when Try again is clicked", () => {
    const retry = vi.fn();
    findButton(ErrorPage({ error: new Error("x"), retry }))?.onClick();
    expect(retry).toHaveBeenCalledOnce();
  });
});
