import RunForm from "@/components/RunForm";
import { getReplayCatalog } from "@/lib/jobs/server";
import PageHeader from "@/components/PageHeader";
import ScopeNote from "@/components/ScopeNote";
import Page from "@/components/Page";
import Button from "@/components/Button";

export default async function RunPage() {
  const { data: catalog } = await getReplayCatalog();
  return (
    <Page>
      <PageHeader
        eyebrow="Local historical replay"
        title="New run"
        aside={<Button href="/runs">Run history</Button>}
      />
      <ScopeNote>
        Replays a past market window on paper. The synthetic fixture only checks correctness.
        Queuing a run never starts data collection or trading.
      </ScopeNote>
      <RunForm catalog={catalog} />
    </Page>
  );
}
