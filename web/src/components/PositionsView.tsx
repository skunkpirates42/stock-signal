"use client";

import { useEffect, useState } from "react";
import { startVisiblePolling } from "@/lib/polling";
import { observationFresh, type PositionState } from "@/lib/execution";
import { formatPrice, formatTimestamp } from "@/lib/format";
import OpenPositions from "./OpenPositions";
import FillsTable from "./FillsTable";
import PositionExecution from "./PositionExecution";

export default function PositionsView() {
  const [data, setData] = useState<PositionState | null>(null);
  const [failed, setFailed] = useState(false);
  const [now, setNow] = useState(() => new Date());
  const [account, setAccount] = useState("");
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timer = setInterval(() => setNow(new Date()), 1000);
    const stop = startVisiblePolling(
      async () => {
        try {
          const response = await fetch("/api/position-state", {
            cache: "no-store",
            signal: AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]),
          });
          if (!response.ok) throw new Error("Unavailable");
          const next: PositionState = await response.json();
          if (
            !Array.isArray(next.positions) ||
            !Array.isArray(next.accounts) ||
            !Array.isArray(next.pending_entries) ||
            !Array.isArray(next.exit_fills) ||
            !Array.isArray(next.closed_trades)
          )
            throw new Error("Invalid response");
          if (active) {
            setData(next);
            setFailed(false);
          }
        } catch {
          if (active) setFailed(true);
        }
      },
      document,
      5000,
    );
    return () => {
      active = false;
      controller.abort();
      stop();
      clearInterval(timer);
    };
  }, []);
  if (!data)
    return (
      <p role="status">
        {failed
          ? "Position state unavailable. Account holdings are unknown."
          : "Loading position state…"}
      </p>
    );
  const selected = account || data.accounts[0]?.account;
  const scope = data.accounts.find((item) => item.account === selected);
  const current = !failed && observationFresh(data.fetched_at, now, data.stale_seconds);
  const brokerCurrent =
    current && !!scope && observationFresh(scope.observed_at, now, data.stale_seconds);
  const positions = data.positions.filter(
    (p) => p.provenance !== "Alpaca paper" || p.account === selected,
  );
  return (
    <>
      {failed && (
        <p role="status">
          Position service unavailable. Showing last-known data; current holdings and protection are
          unconfirmed.
        </p>
      )}
      {!current && <p role="status">Position data is stale. Current protection is unconfirmed.</p>}
      <p className="micro">
        Endpoint fetched: {formatTimestamp(data.fetched_at)}. Broker observations and IEX price
        times are separate.
      </p>
      <section aria-label="Paper account status">
        <h2>Alpaca paper account</h2>
        {data.accounts.length > 0 ? (
          <label>
            Selected account{" "}
            <select value={selected} onChange={(event) => setAccount(event.target.value)}>
              {data.accounts.map((item) => (
                <option key={item.account} value={item.account}>
                  {item.account}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <p>
            No observed paper account. Broker holdings unavailable; this does not confirm an empty
            account.
          </p>
        )}
        {scope && (
          <>
            <p role="status">
              Account: {brokerCurrent ? scope.status : "stale / unavailable"} · observation result:{" "}
              {scope.observation_status}
            </p>
            <p>
              Last broker observation: {formatTimestamp(scope.observed_at)} · last successful
              reconciliation: {formatTimestamp(scope.reconciled_at)}
            </p>
            <p>
              Worker heartbeat: {formatTimestamp(scope.heartbeat_at)} ·{" "}
              {observationFresh(scope.heartbeat_at, now, data.stale_seconds)
                ? scope.worker_status
                : "stale / unknown"}
            </p>
            {scope.mismatch && (
              <p role="status">
                Journal/broker mismatch. Broker: {JSON.stringify(scope.broker_positions)}; journal:{" "}
                {JSON.stringify(scope.journal_positions)}. No repair is performed here.
              </p>
            )}
          </>
        )}
        {data.pending_entries
          .filter((entry) => entry.account === selected)
          .map((entry) => (
            <div className="card" key={entry.id}>
              <p>
                {entry.ticker} · pending Alpaca paper entry · {entry.state}
              </p>
              <p>
                Requested {entry.requested_qty} · filled {entry.filled_qty} · actual average{" "}
                {formatPrice(entry.fill_price)} · protection awaiting entry fill
              </p>
              {entry.pending_exit && <p>Pending exit: {entry.pending_exit}</p>}
              {Object.entries(entry.execution?.legs ?? {}).map(([kind, leg]) => (
                <p key={kind}>
                  {kind === "stop" ? "Stop" : "Target"}{" "}
                  {formatPrice(kind === "stop" ? entry.stop : entry.target)} · {leg.state}
                  {leg.state === "held" ? " · awaiting activation" : ""}
                  {" · not confirmed active"}
                  {!brokerCurrent || !observationFresh(leg.updated_at ?? null, now)
                    ? " · observation stale/unknown"
                    : ""}
                </p>
              ))}
            </div>
          ))}
        {positions
          .filter((p) => p.execution)
          .map((p) => (
            <PositionExecution
              key={p.id}
              position={p}
              current={brokerCurrent && !scope?.mismatch}
              now={now}
            />
          ))}
      </section>
      <OpenPositions positions={positions} now={now} />
      <section aria-label="Actual broker exit fills">
        <h2>Actual broker exit fills</h2>
        <p className="micro">
          Confirmed cumulative fills from the journal; prices below are broker fills, not IEX
          estimates.
        </p>
        {data.exit_fills
          .filter((fill) => fill.account === selected)
          .map((fill) => (
            <p key={fill.id}>
              {fill.ticker} · {fill.reason ?? "exit"} · {fill.state} · {fill.filled_qty} shares at{" "}
              {formatPrice(fill.fill_price)} · recorded {formatTimestamp(fill.updated_at)}
            </p>
          ))}
      </section>
      <FillsTable
        trades={data.closed_trades.filter(
          (trade) => trade.backend !== "alpaca" || trade.account === selected,
        )}
      />
    </>
  );
}
