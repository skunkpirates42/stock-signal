import { observationFresh, type PositionState } from "./execution";

export function deriveAccountPositionView({
  positionState,
  requestedAccount,
  pollFailed,
  now,
}: {
  positionState: PositionState;
  requestedAccount: string;
  pollFailed: boolean;
  now: Date;
}) {
  const selectedAccount = positionState.accounts.some(
    (observation) => observation.account === requestedAccount,
  )
    ? requestedAccount
    : positionState.accounts[0]?.account;
  const accountObservation = positionState.accounts.find(
    (observation) => observation.account === selectedAccount,
  );
  const isPositionStateCurrent =
    !pollFailed && observationFresh(positionState.fetched_at, now, positionState.stale_seconds);
  const isBrokerObservationCurrent =
    isPositionStateCurrent &&
    !!accountObservation &&
    observationFresh(accountObservation.observed_at, now, positionState.stale_seconds);
  const positions = positionState.positions.filter(
    (position) => position.provenance !== "Alpaca paper" || position.account === selectedAccount,
  );

  return {
    selectedAccount,
    accountObservation,
    accounts: positionState.accounts,
    fetchedAt: positionState.fetched_at,
    isPositionStateCurrent,
    isBrokerObservationCurrent,
    isExecutionCurrent: isBrokerObservationCurrent && !accountObservation?.mismatch,
    statusNeedsAttention: !isPositionStateCurrent || !!accountObservation?.mismatch,
    statusLabel: pollFailed
      ? "Position service unavailable"
      : !isPositionStateCurrent
        ? "Position data is stale"
        : accountObservation
          ? isBrokerObservationCurrent
            ? accountObservation.status
            : "Broker observation stale / unavailable"
          : "No account observed",
    protectionWarning: pollFailed
      ? "Showing last-known data; current holdings and protection are unconfirmed."
      : !isPositionStateCurrent
        ? "Current protection is unconfirmed."
        : null,
    workerStatus:
      accountObservation &&
      observationFresh(accountObservation.heartbeat_at, now, positionState.stale_seconds)
        ? accountObservation.worker_status
        : "stale / unknown",
    positions,
    executionPositions: positions.filter((position) => position.execution),
    pendingEntries: positionState.pending_entries.filter(
      (entry) => entry.account === selectedAccount,
    ),
    exitFills: positionState.exit_fills.filter((fill) => fill.account === selectedAccount),
    closedTrades: positionState.closed_trades.filter(
      (trade) => trade.backend !== "alpaca" || trade.account === selectedAccount,
    ),
  };
}

export type AccountPositionView = ReturnType<typeof deriveAccountPositionView>;
