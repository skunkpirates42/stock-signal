"use client";

import { useState } from "react";
import { usePolledResource } from "@/hooks/usePolledResource";
import { useVisibleClock } from "@/hooks/useVisibleClock";
import { deriveAccountPositionView } from "@/lib/accountPositionView";
import { newerOf } from "@/lib/polledResource";
import { readPositionState } from "@/lib/execution";
import OpenPositions from "./OpenPositions";
import FillsTable from "./FillsTable";
import PaperAccountStatus from "./PaperAccountStatus";
import ExitFills from "./ExitFills";

export default function PositionsView() {
  const {
    data: positionState,
    failed: pollFailed,
    checkedAt,
  } = usePolledResource("/api/position-state", readPositionState, 5000);
  // A response can land between one-second clock ticks; judge freshness from whichever is later.
  const now = newerOf(useVisibleClock(1000), checkedAt);
  const [requestedAccount, setRequestedAccount] = useState("");
  if (!positionState)
    return (
      <p role="status">
        {pollFailed
          ? "Position state unavailable. Account holdings are unknown."
          : "Loading position state…"}
      </p>
    );
  const view = deriveAccountPositionView({ positionState, requestedAccount, pollFailed, now });
  return (
    <div className="stack stack-section">
      <PaperAccountStatus view={view} onAccountChange={setRequestedAccount} now={now} />
      <OpenPositions positions={view.positions} now={now} />
      <ExitFills fills={view.exitFills} />
      <FillsTable trades={view.closedTrades} />
    </div>
  );
}
