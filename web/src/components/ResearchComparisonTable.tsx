import Link from "next/link";
import DataTable from "@/components/DataTable";
import type { ComparisonTable } from "@/lib/research-comparison";

export interface ResearchComparisonTableProps {
  table: ComparisonTable;
}

export default function ResearchComparisonTable({ table }: ResearchComparisonTableProps) {
  return (
    <section className="research-comparison">
      <DataTable>
        <caption className="sr-only">Realized net P&amp;L by variant and window</caption>
        <thead>
          <tr>
            <th scope="col">Variant</th>
            {table.columns.map((column) => (
              <th scope="col" key={column.key} title={column.exactRange}>
                <span className="research-window-name">{column.name}</span>
                <span className="research-window-dates">{column.dates}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row) => (
            <tr key={row.variant}>
              <th scope="row">{row.variant}</th>
              {row.cells.map((entries, index) => (
                <td key={table.columns[index].key}>
                  {entries.length === 0 && (
                    <span className="research-cell-empty">No saved result</span>
                  )}
                  {entries.map((entry) => (
                    <div className="research-cell" key={entry.id}>
                      <Link className={`num tone-${entry.tone}`} href={`/research/${entry.id}`}>
                        {entry.pnlLabel}
                        <span className="sr-only">
                          {" "}
                          for {table.columns[index].name} / {row.variant}
                        </span>
                      </Link>
                      {entry.synthetic && (
                        <span className="research-cell-flag">Synthetic correctness</span>
                      )}
                      {entry.retrospective === true && (
                        <span className="research-cell-note">Retrospective</span>
                      )}
                      {entry.retrospective === false && (
                        <span className="research-cell-note">Not retrospective</span>
                      )}
                      {entry.coverage !== null && (
                        <span className="research-cell-note">Accounting {entry.coverage}</span>
                      )}
                    </div>
                  ))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </DataTable>
      <ul className="research-footnotes">
        <li>Cells show realized net P&amp;L. Open a cell for the saved result.</li>
        {table.columns.map((column) => (
          <li key={column.key}>
            {column.name}: {column.exactRange}.
          </li>
        ))}
        {table.sharedRetrospective === true && (
          <li>Every result here is retrospective research.</li>
        )}
        {table.sharedCoverage !== null && (
          <li>Accounting coverage is {table.sharedCoverage} for every result here.</li>
        )}
      </ul>
    </section>
  );
}
