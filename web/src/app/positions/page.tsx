import PositionsView from "@/components/PositionsView";
import PageHeader from "@/components/PageHeader";
import Page from "@/components/Page";

export default function PositionsPage() {
  return (
    <Page className="stack stack-section">
      <div className="stack">
        <PageHeader title="Positions" />
        <p>
          Paper-broker observations, saved local simulations, replay and unknown provenance are
          labeled separately. Market prices do not establish broker holdings or protection.
        </p>
      </div>
      <PositionsView />
    </Page>
  );
}
