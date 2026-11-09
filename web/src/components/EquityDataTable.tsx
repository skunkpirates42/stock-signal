import DataTable from "@/components/DataTable";
import type { EquityPoint } from "@/lib/types";
import { formatBalance, formatTimestamp } from "@/lib/format";

export default function EquityDataTable({ points }: { points: EquityPoint[] }) {
  return (
    <DataTable caption="Equity data">
      <thead>
        <tr>
          <th scope="col">Time (UTC)</th>
          <th scope="col" className="num">
            Equity
          </th>
        </tr>
      </thead>
      <tbody>
        {points.map((point, index) => (
          <tr key={`${point.label}-${index}`}>
            <td>{formatTimestamp(point.label)}</td>
            <td className="num">{formatBalance(point.equity)}</td>
          </tr>
        ))}
      </tbody>
    </DataTable>
  );
}
