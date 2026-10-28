import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { describeStatus } from "@/lib/health";
import StatusLine from "./StatusLine";

it.each(["blocked", "stopped", "unresolved", "incomplete"])(
  "shows %s in the collapsed summary even with a fresh heartbeat",
  (status) => {
    const checkedAt = "2026-06-10T14:00:00Z";
    const summary = describeStatus({
      source: "live",
      apiFailed: false,
      checkedAt,
      status: {
        latest_bar: null,
        unresolved_orders: [],
        runtime: [
          {
            scope: "live:local:paper",
            status,
            updated_at: checkedAt,
            data_at: null,
            detail: "ValueError: forced failure; failed batch not retried",
          },
        ],
      },
    });
    const html = renderToStaticMarkup(createElement(StatusLine, { summary, error: null }));
    const collapsed = html.match(/<summary>(.*?)<\/summary>/)?.[1];
    expect(collapsed).toContain("Heartbeat fresh");
    expect(collapsed).toContain(`live:local:paper: ${status}`);
    expect(collapsed).toContain('class="status-attention"');
    expect(html).toContain("ValueError: forced failure; failed batch not retried");
  },
);

it.each(["open", "closed", "unavailable"])(
  "shows global market %s in the collapsed status",
  (state) => {
    const summary = describeStatus({
      source: null,
      status: null,
      apiFailed: false,
      checkedAt: null,
    });
    const html = renderToStaticMarkup(
      createElement(StatusLine, {
        summary,
        error: null,
        marketLabel: `US regular market: ${state}`,
        marketCheckedAt: "2026-10-28T15:00:00Z",
      }),
    );
    expect(html.match(/<summary>(.*?)<\/summary>/)?.[1]).toContain(`US regular market: ${state}`);
    expect(html).toContain("extended hours are excluded");
  },
);
