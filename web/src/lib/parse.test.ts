import { expect, it } from "vitest";
import {
  readArrayOf,
  readFields,
  readLiteral,
  readNullable,
  readNumber,
  readOptional,
  readRecordOf,
  readString,
  ResponseShapeError,
} from "./parse";

it("names the path and expectation of the field that failed", () => {
  const readRow = (value: unknown, path: string) => readFields(value, path)("qty", readNumber);
  expect(() => readArrayOf(readRow)([{ qty: 1 }, { qty: "2" }], "rows")).toThrow(
    new ResponseShapeError("rows[1].qty", "finite number"),
  );
  expect(() => readRecordOf(readNumber)({ SPY: 1, QQQ: null }, "prices")).toThrow(
    "prices.QQQ: expected finite number",
  );
});

it("rejects values that JSON can carry but money fields cannot use", () => {
  expect(() => readNumber(Number.NaN, "x")).toThrow(ResponseShapeError);
  expect(() => readNumber("1.5", "x")).toThrow(ResponseShapeError);
  expect(() => readFields([], "x")).toThrow("x: expected object");
  expect(() => readFields(null, "x")).toThrow("x: expected object");
});

it("distinguishes nullable, optional and literal fields", () => {
  expect(readNullable(readString)(null, "x")).toBeNull();
  expect(() => readNullable(readString)(undefined, "x")).toThrow(ResponseShapeError);
  expect(readOptional(readString)(undefined, "x")).toBeUndefined();
  expect(readLiteral("iex")("iex", "feed")).toBe("iex");
  expect(() => readLiteral("iex", "sip")("otc", "feed")).toThrow("feed: expected iex | sip");
});
