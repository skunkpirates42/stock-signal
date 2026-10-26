import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import AvailableValue from "@/components/AvailableValue";
import DataTable from "@/components/DataTable";
import StatTile from "@/components/StatTile";
import type { Metric } from "@/lib/demo";
import { describeObservation } from "@/lib/observation";
import { headlineFigures, savedMetricGroups } from "@/lib/savedResult";

const unavailable: Metric = {
  observation: {
    availability: "unavailable",
    value: null,
    reason: "not_recorded",
    detail: "Fees were not saved.",
  },
  unit: "USD",
  basis: "Fixture",
  source_pointer: null,
};

function visibleText(element: Parameters<typeof renderToStaticMarkup>[0]) {
  return renderToStaticMarkup(element).replace(/<[^>]*>/g, " ");
}

describe("primitives with nothing to show", () => {
  it("AvailableValue renders an unavailable or missing metric without a number", () => {
    for (const metric of [unavailable, undefined]) {
      expect(
        visibleText(createElement(AvailableValue, describeObservation("fees", metric))),
      ).not.toMatch(/\d/);
    }
  });

  it("AvailableValue renders every row of an empty result without a number", () => {
    const rows = savedMetricGroups({}).flatMap((group) => group.rows);
    for (const row of rows)
      expect(visibleText(createElement(AvailableValue, row.value))).not.toMatch(/\d/);
  });

  it("AvailableValue shows the reason as visible text, not a hover-only title", () => {
    const element = createElement(AvailableValue, describeObservation("fees", unavailable));
    expect(renderToStaticMarkup(element)).not.toContain("title=");
    expect(visibleText(element)).toContain("Fees were not saved.");
  });

  it("StatTile renders every headline of an empty result without a number", () => {
    for (const figure of headlineFigures({}))
      expect(visibleText(createElement(StatTile, figure))).not.toMatch(/\d/);
  });

  it("DataTable renders its empty row without a number", () => {
    const emptyRow = createElement(
      "tbody",
      null,
      createElement(
        "tr",
        null,
        createElement("td", { colSpan: 3, className: "data-table-empty" }, "No rows."),
      ),
    );
    expect(visibleText(createElement(DataTable, null, emptyRow))).not.toMatch(/\d/);
  });
});
