import type { AccountPositionView } from "@/lib/accountPositionView";
import { formatTimestamp } from "@/lib/format";
import Disclosure from "./Disclosure";
import PendingEntries from "./PendingEntries";
import PositionExecution from "./PositionExecution";

export default function PaperAccountStatus({
  view,
  onAccountChange,
  now,
}: {
  view: AccountPositionView;
  onAccountChange: (account: string) => void;
  now: Date;
}) {
  const { accountObservation } = view;
  return (
    <aside className="status-line" aria-label="Paper account status">
      <Disclosure
        summary={
          <>
            <span>Alpaca paper account</span>
            <span
              role="status"
              className={view.statusNeedsAttention ? "status-attention" : undefined}
            >
              {view.statusLabel}
            </span>
          </>
        }
      >
        <div className="status-detail stack stack-detail">
          {view.protectionWarning && <p>{view.protectionWarning}</p>}
          <p>
            Endpoint fetched: {formatTimestamp(view.fetchedAt)}. Broker observations and IEX price
            times are separate.
          </p>
          {view.accounts.length > 0 ? (
            <label>
              Selected account{" "}
              <select
                value={view.selectedAccount}
                onChange={(event) => onAccountChange(event.target.value)}
              >
                {view.accounts.map((observation) => (
                  <option key={observation.account} value={observation.account}>
                    {observation.account}
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
          {accountObservation && (
            <div className="stack stack-detail">
              <p role="status">
                Account:{" "}
                {view.isBrokerObservationCurrent
                  ? accountObservation.status
                  : "stale / unavailable"}{" "}
                · observation result: {accountObservation.observation_status}
              </p>
              <p>
                Last broker observation: {formatTimestamp(accountObservation.observed_at)} · last
                successful reconciliation: {formatTimestamp(accountObservation.reconciled_at)}
              </p>
              <p>
                Worker heartbeat: {formatTimestamp(accountObservation.heartbeat_at)} ·{" "}
                {view.workerStatus}
              </p>
              {accountObservation.mismatch && (
                <p role="status">
                  Journal/broker mismatch. Broker:{" "}
                  {JSON.stringify(accountObservation.broker_positions)}; journal:{" "}
                  {JSON.stringify(accountObservation.journal_positions)}. No repair is performed
                  here.
                </p>
              )}
            </div>
          )}
          <section className="stack" aria-label="Paper execution status">
            <PendingEntries
              entries={view.pendingEntries}
              isBrokerObservationCurrent={view.isBrokerObservationCurrent}
              now={now}
            />
            {view.executionPositions.map((position) => (
              <PositionExecution
                key={position.id}
                position={position}
                current={view.isExecutionCurrent}
                now={now}
              />
            ))}
          </section>
        </div>
      </Disclosure>
    </aside>
  );
}
