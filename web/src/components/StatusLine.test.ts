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
