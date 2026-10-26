import type { ReactNode } from "react";

export interface DataTableProps {
  compact?: boolean;
  children: ReactNode;
}

export default function DataTable({ compact = false, children }: DataTableProps) {
  return (
    <div className="table-scroll">
      <table className={compact ? "data-table data-table-compact" : "data-table"}>{children}</table>
    </div>
  );
}
