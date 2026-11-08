import type { ReactNode } from "react";

export interface DataTableProps {
  caption: string;
  compact?: boolean;
  children?: ReactNode;
}

export default function DataTable({ caption, compact = false, children }: DataTableProps) {
  return (
    <div
      className="table-scroll"
      role="region"
      aria-label={`${caption} table scroll area`}
      tabIndex={0}
    >
      <table className={compact ? "data-table data-table-compact" : "data-table"}>
        <caption className="sr-only">{caption}</caption>
        {children}
      </table>
    </div>
  );
}
