import { describe, expect, it, vi } from "vitest";
import { Children, isValidElement, type ReactNode } from "react";
import GlobalError from "./global-error";

function textOf(node: unknown): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (!isValidElement<{ children?: ReactNode }>(node)) return "";
  return Children.toArray(node.props.children)
    .map((child) => textOf(child))
    .join("");
}

function findByType(node: unknown, type: string): { props: Record<string, unknown> } | undefined {
  if (!isValidElement<{ children?: ReactNode }>(node)) return undefined;
  if (node.type === type) return { props: node.props as Record<string, unknown> };
  for (const child of Children.toArray(node.props.children)) {
    const found = findByType(child, type);
    if (found) return found;
  }
  return undefined;
}

describe("global error page", () => {
  it("renders its own document, since it replaces the root layout", () => {
    const page = GlobalError({ error: new Error("layout broke"), retry: () => {} });
    expect(isValidElement(page) && page.type).toBe("html");
    expect(findByType(page, "body")).toBeDefined();
    expect(findByType(page, "title")?.props.children).toBe("Something went wrong");
  });

  it("shows the error message and, when present, the digest", () => {
    const error = Object.assign(new Error("layout broke"), { digest: "abc123" });
    const text = textOf(GlobalError({ error, retry: () => {} }));
    expect(text).toContain("layout broke");
    expect(text).toContain("abc123");
  });

  it("retries when Try again is clicked", () => {
    const retry = vi.fn();
    const button = findByType(GlobalError({ error: new Error("x"), retry }), "button");
    (button?.props.onClick as () => void)();
    expect(retry).toHaveBeenCalledOnce();
  });
});
