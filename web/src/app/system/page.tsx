import AvailableValue from "@/components/AvailableValue";
import Card from "@/components/Card";
import DataTable from "@/components/DataTable";
import Disclosure from "@/components/Disclosure";
import StatTile from "@/components/StatTile";
import { formatCurrency, toneForSign } from "@/lib/format";
import { describeObservation } from "@/lib/observation";
import { COLOR_TOKENS, OBSERVATIONS, STAT_TILES, TABLE_ROWS, TYPE_SCALE } from "./fixtures";
import PageHeader from "@/components/PageHeader";
import ScopeNote from "@/components/ScopeNote";
import Page from "@/components/Page";

function sampleTable(rows: typeof TABLE_ROWS, compact = false) {
  return <DataTable compact={compact}>
    <thead><tr><th>Symbol</th><th className="num">Trades</th><th className="num">P&amp;L</th></tr></thead>
    <tbody>
      {rows.map((row) => <tr key={row.symbol}>
        <td>{row.symbol}</td><td className="num">{row.trades}</td><td className={`num tone-${toneForSign(row.pnl)}`}>{formatCurrency(row.pnl)}</td>
      </tr>)}
      {rows.length === 0 && <tr><td colSpan={3} className="data-table-empty">No rows.</td></tr>}
    </tbody>
  </DataTable>;
}

export default function SystemPage() {
  return <Page className="system">
    <PageHeader eyebrow="Reference" title="Design system" />
    <ScopeNote>Every shared component in each of its states, built from fixtures. Nothing here calls the API.</ScopeNote>

    <Card title="Color tokens">
      <div className="system-swatches">{COLOR_TOKENS.map((token) => <figure className="system-swatch" key={token}>
        <div className="system-swatch-chip" style={{ background: `var(${token})` }} />
        <figcaption className="num">{token}</figcaption>
      </figure>)}</div>
    </Card>

    <Card title="Type scale">
      {TYPE_SCALE.map((token) => <div className="system-type-row" key={token}>
        <span className="num note">{token}</span><span style={{ fontSize: `var(${token})` }}>Realized net P&amp;L</span>
      </div>)}
    </Card>

    <Card title="AvailableValue" note="An unavailable value shows its reason beneath it. Unavailable never renders as zero.">
      <DataTable>
        <thead><tr><th>State</th><th className="num">Rendered</th></tr></thead>
        <tbody>{OBSERVATIONS.map(({ state, name, metric }) =>
          <tr key={state}><td>{state}</td><td className="num"><AvailableValue {...describeObservation(name, metric)} /></td></tr>)}</tbody>
      </DataTable>
    </Card>

    <h2 className="micro">StatTile</h2>
    <div className="stat-grid">{STAT_TILES.map((tile) => <StatTile key={tile.label} {...tile} />)}</div>

    <div className="system-grid">
      <Card title="Card with a heading" note="The note prop sits under the title.">Body content.</Card>
      <Card title="Card with a label" titleVariant="label">Body content.</Card>
      <Card><p className="card-note">A card without a title.</p></Card>
    </div>

    <div className="system-grid">
      <Disclosure className="card" summary="Disclosure, closed"><p className="card-note">Hidden until opened.</p></Disclosure>
      <Disclosure className="card" open summary="Disclosure, open"><p className="card-note">Shown because the open prop is set.</p></Disclosure>
    </div>

    <Card title="DataTable">{sampleTable(TABLE_ROWS)}</Card>
    <Card title="DataTable, compact">{sampleTable(TABLE_ROWS, true)}</Card>
    <Card title="DataTable, empty">{sampleTable([])}</Card>
  </Page>;
}
