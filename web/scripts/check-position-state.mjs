// Offline browser acceptance. Supply PUPPETEER_PATH for an installed puppeteer package;
// run against a temporary local Next server via POSITION_TEST_URL. All API calls are mocked.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const loadPackage = createRequire(import.meta.url);
const puppeteer = loadPackage(process.env.PUPPETEER_PATH || "puppeteer");
const stamp = () => new Date().toISOString();
const order = (id, state = "new") => ({
  id,
  state,
  requested_qty: 10,
  filled_qty: 0,
  fill_price: null,
  updated_at: stamp(),
  ticker: "SPY",
  purpose: "exit",
});
const leg = (id) => ({ ...order(id), coverage: true, current: true, quantity: 10 });
const trade = (id, backend = "alpaca", source = "live") => ({
  id,
  ticker: "SPY",
  direction: "LONG",
  entry: 100,
  stop: 95,
  target: 110,
  shares: 10,
  remaining_shares: 10,
  entry_at: stamp(),
  created_at: stamp(),
  outcome: "OPEN",
  pnl: null,
  exit_price: null,
  closed_at: null,
  source,
  backend,
  account: "account-a",
  provenance:
    backend === "alpaca" ? "Alpaca paper" : source === "backtest" ? "Replay" : "Local simulation",
  execution: null,
});
const scope = (account) => ({
  account,
  status: "observed",
  mismatch: false,
  observed_at: stamp(),
  reconciled_at: stamp(),
  heartbeat_at: stamp(),
  observation_status: "ok",
  worker_status: "running",
  broker_positions: { SPY: 10 },
  journal_positions: { SPY: 10 },
});
const fixture = () => ({
  fetched_at: stamp(),
  stale_seconds: 30,
  accounts: [scope("account-a"), scope("account-b")],
  positions: [
    {
      ...trade(1),
      execution: {
        entry: { ...order("parent", "filled"), filled_qty: 10, fill_price: 100 },
        protection: "confirmed",
        pending_exit: null,
        legs: { stop: leg("stop"), target: leg("target") },
      },
    },
    trade(2, "local"),
    trade(3, "local", "backtest"),
    { ...trade(4, null, null), account: null, provenance: "Unknown provenance" },
    { ...trade(5), account: "account-b", execution: null },
  ],
  pending_entries: [
    {
      ...order("pending", "new"),
      account: "account-a",
      pending_exit: null,
      stop: 95,
      target: 110,
      execution: {
        legs: {
          stop: { ...leg("held-stop"), state: "held" },
          target: { ...leg("rejected-target"), state: "rejected" },
        },
      },
    },
  ],
  exit_fills: [],
  closed_trades: [],
});
(async () => {
  const browser = await puppeteer.launch({
    executablePath:
      process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    headless: true,
    args: ["--no-sandbox"],
  });
  try {
    const page = await browser.newPage();
    page.on("pageerror", (error) => console.log("Page error:", error.message));
    await page.setViewport({ width: 1280, height: 1100 });
    let data = fixture(),
      failure = false,
      requests = 0,
      stalled = false,
      ageChildOnResponse = false;
    await page.setRequestInterception(true);
    page.on("request", (req) => {
      const url = new URL(req.url());
      if (url.pathname === "/api/position-state") {
        requests++;
        if (ageChildOnResponse)
          data.positions[0].execution.legs.stop.updated_at = new Date(
            Date.now() - 29000,
          ).toISOString();
        if (stalled) return; // abort timeout belongs to the client
        return req.respond({
          status: failure ? 503 : 200,
          contentType: "application/json",
          body: JSON.stringify(failure ? { error: "unavailable" } : data),
        });
      }
      if (url.pathname === "/api/position-prices")
        return req.respond({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ prices: { SPY: { price: 101, timestamp: stamp() } } }),
        });
      if (url.pathname.startsWith("/api/") || req.method() === "POST")
        return req.respond({ status: 503, body: "fixture unavailable" });
      return req.continue();
    });
    await page.bringToFront();
    await page.goto(process.env.POSITION_TEST_URL || "http://127.0.0.1:3105/positions");
    const contains = async (text) => {
      console.log("Checking:", text);
      try {
        return await page.waitForFunction(
          (text) => document.body.innerText.includes(text),
          { timeout: 15000 },
          text,
        );
      } catch (error) {
        console.log(await page.$eval("body", (e) => e.innerText));
        throw error;
      }
    };
    await contains("Protection confirmed at last observation");
    const body = await page.$eval("body", (e) => e.innerText);
    for (const label of [
      "Local simulation",
      "Replay",
      "Unknown provenance",
      "held",
      "rejected",
      "awaiting activation",
    ])
      assert(body.toLowerCase().includes(label.toLowerCase()), label);
    await page.screenshot({
      path: process.env.POSITION_SCREENSHOT || "/tmp/issue-105-positions.png",
      fullPage: true,
    });
    await page.select("select", "account-b");
    await page.waitForFunction(() => !document.body.innerText.includes("trade #1"));
    assert(!(await page.$eval("body", (e) => e.innerText)).includes("pending Alpaca paper entry"));
    await page.select("select", "account-a");
    await contains("trade #1");
    failure = true;
    await contains("Position service unavailable");
    await contains("trade #1"); // retain last-known account data on failure
    assert(
      !(await page.$eval("body", (e) => e.innerText)).includes(
        "Protection confirmed at last observation",
      ),
    );
    failure = false;
    data = fixture();
    ageChildOnResponse = true;
    await contains("Protection confirmed at last observation");
    stalled = true;
    await contains("Warning: current protection is not confirmed");
    await contains("observation stale/unknown");
    stalled = false;
    ageChildOnResponse = false;
    data = fixture();
    data.positions = data.positions.filter((p) => p.id !== 1);
    data.pending_entries = [];
    data.accounts[0] = {
      ...scope("account-a"),
      status: "confirmed empty",
      broker_positions: {},
      journal_positions: {},
    };
    data.exit_fills = [
      {
        ...order("stop", "filled"),
        account: "account-a",
        filled_qty: 10,
        fill_price: 94,
        reason: "stop",
      },
    ];
    data.closed_trades = [
      {
        ...trade(1),
        outcome: "LOSS",
        remaining_shares: 0,
        pnl: -60,
        exit_price: 94,
        exit_at: stamp(),
      },
    ];
    await contains("10 shares at $94.00");
    await contains("confirmed empty");
    assert(!(await page.$eval("body", (e) => e.innerText)).includes("trade #1"));
    assert(requests >= 4);
    await page.setViewport({ width: 390, height: 844 });
    assert(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      "mobile horizontal overflow",
    );
    console.log(
      JSON.stringify({
        passed: true,
        checks: [
          "provenance",
          "held/rejected pending children",
          "account switching",
          "poll updates",
          "failure retention",
          "child stale expiry",
          "closed exit fill",
          "confirmed empty",
          "mobile width",
        ],
        requests,
      }),
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
