// @vitest-environment jsdom

import { createElement } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ResponseShapeError } from "@/lib/parse";
import ErrorPage from "./error";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it.each([
  [new TypeError("secret token in rendering message"), "unexpected"],
  [new ResponseShapeError("private account payload", "number"), "schema"],
  [new SyntaxError("raw JSON body"), "json"],
])("uses a neutral fallback and sanitized diagnostics", (error, category) => {
  const log = vi.spyOn(console, "error").mockImplementation(() => {});
  Object.assign(error, { digest: "abc123" });
  const retry = vi.fn();
  const view = render(createElement(ErrorPage, { error, retry }));
  expect(view.container.textContent).toContain("This dashboard view could not be loaded");
  expect(view.container.textContent).not.toContain("Flask API");
  expect(view.container.textContent).not.toContain(error.message);
  expect(view.container.textContent).toContain(`Failure category: ${category}`);
  expect(view.container.textContent).toContain("Error reference: abc123");
  expect(log.mock.calls).toEqual([
    ["web_failure", { resource: "route", category, reference: "abc123" }],
  ]);
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(retry).toHaveBeenCalledOnce();
  view.rerender(createElement(ErrorPage, { error, retry }));
  expect(log).toHaveBeenCalledOnce();
});

it("omits an unsafe reference without exposing it in markup or logs", () => {
  const log = vi.spyOn(console, "error").mockImplementation(() => {});
  const error = Object.assign(new Error("private details"), { digest: "Authorization: secret\n" });
  const view = render(createElement(ErrorPage, { error, retry: vi.fn() }));
  expect(view.container.textContent).not.toContain("Error reference:");
  expect(JSON.stringify(log.mock.calls)).not.toContain("secret");
});
