"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import Disclosure from "@/components/Disclosure";
import Card from "@/components/Card";
import EquityDataTable from "@/components/EquityDataTable";
import type { EquityPoint } from "@/lib/types";
import { summarizeEquityCurve } from "@/lib/equity";

const EquityChart = dynamic(() => import("@/components/EquityChart"), {
  ssr: false,
  loading: () => <p className="equity-chart-loading">Loading chart…</p>,
});

export interface EquityCurveProps {
  points: EquityPoint[];
}

export default function EquityCurve({ points }: EquityCurveProps) {
  const [hasOpenedData, setHasOpenedData] = useState(false);

  if (points.length < 2) {
    return (
      <Card title="Equity" titleVariant="label" className="equity-curve">
        <p className="equity-curve-empty">Not enough closed trades to plot</p>
      </Card>
    );
  }

  return (
    <Card title="Equity" titleVariant="label" className="equity-curve">
      <p className="card-note">{summarizeEquityCurve(points)}</p>
      <div className="equity-chart-slot">
        <EquityChart points={points} />
      </div>
      <Disclosure
        className="equity-data"
        summary="View equity data"
        onToggle={(open) => open && setHasOpenedData(true)}
      >
        {hasOpenedData && <EquityDataTable points={points} />}
      </Disclosure>
    </Card>
  );
}
