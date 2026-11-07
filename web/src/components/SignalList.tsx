"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import type { SignalSearchResult } from "@/lib/types";
import type { SignalCriteria } from "@/lib/filters";
import { signalSearchHref, type SignalQuery } from "@/lib/signalSearch";
import FilterBar from "@/components/FilterBar";
import SignalRow from "@/components/SignalRow";
import Button from "@/components/Button";

export interface SignalListProps {
  result: SignalSearchResult;
  query: SignalQuery;
}

export default function SignalList({ result, query }: SignalListProps) {
  const router = useRouter();
  const [criteria, setCriteria] = useState<SignalCriteria>(query);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [isPending, startTransition] = useTransition();
  const invalidDateRange = !!(criteria.from && criteria.to && criteria.from > criteria.to);
  const first = result.total ? (result.page - 1) * result.page_size + 1 : 0;
  const last = first ? first + result.items.length - 1 : 0;
  const pageHref = (page: number) =>
    signalSearchHref({ ...query, page, snapshotId: result.snapshot_id });
  const resetHref = signalSearchHref({ source: query.source, page: 1, hideWait: true });
  const tickers = Array.from(
    new Set([...result.tickers, ...(query.ticker ? [query.ticker] : [])]),
  ).sort();

  return (
    <div className="signal-list" aria-busy={isPending}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (invalidDateRange) return;
          startTransition(() =>
            router.push(
              signalSearchHref({ ...query, ...criteria, page: 1, snapshotId: undefined }),
              { scroll: false },
            ),
          );
        }}
      >
        <fieldset className="signal-filter-fields" disabled={isPending}>
          <legend className="sr-only">Signal filters</legend>
          <FilterBar criteria={criteria} tickers={tickers} onChange={setCriteria} />
          {invalidDateRange && <p role="alert">From must be on or before To.</p>}
          <div className="date-range-actions">
            <Button type="submit" disabled={invalidDateRange}>
              {isPending ? "Searching…" : "Apply filters"}
            </Button>
            <Link href={resetHref} scroll={false}>
              Reset filters
            </Link>
          </div>
        </fieldset>
      </form>

      <p className="signal-list-count" role="status">
        Showing {first}–{last} of {result.total} matching signals
        {result.hidden_wait_count > 0 &&
          ` · ${result.hidden_wait_count} WAIT hidden by these filters`}
      </p>
      <p className="signal-list-count">
        Newest recorded signals first. Outcomes show the latest trade linked to each signal in the
        same source, backend and account.
      </p>
      {query.snapshotId !== undefined && (
        <p className="signal-list-count">
          Pagination holds the signal set fixed so new arrivals do not move rows between pages.{" "}
          <Link
            href={signalSearchHref({ ...query, page: 1, snapshotId: undefined })}
            scroll={false}
          >
            Include newly recorded signals
          </Link>
        </p>
      )}

      <div className="signal-rows">
        {result.items.map((signal) => (
          <SignalRow
            key={signal.id}
            signal={signal}
            outcome={signal.outcome}
            expanded={expandedId === signal.id}
            onToggle={() => setExpandedId((current) => (current === signal.id ? null : signal.id))}
          />
        ))}
        {result.total === 0 && (
          <p className="signal-list-empty">
            {result.scope_total === 0
              ? "No signals are recorded in this source scope."
              : "No signals match these filters across the complete source scope. Try changing or resetting the filters."}
          </p>
        )}
      </div>
      {result.total_pages > 1 && (
        <nav className="signal-pagination" aria-label="Signal pages">
          {result.page > 1 && (
            <Link href={pageHref(result.page - 1)} scroll={false}>
              Previous page
            </Link>
          )}
          <span>
            Page {result.page} of {result.total_pages}
          </span>
          {result.page < result.total_pages && (
            <Link href={pageHref(result.page + 1)} scroll={false}>
              Next page
            </Link>
          )}
        </nav>
      )}
    </div>
  );
}
