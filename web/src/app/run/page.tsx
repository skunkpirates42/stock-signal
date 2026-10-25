import Link from "next/link";
import RunForm from "@/components/RunForm";
import { getReplayCatalog } from "@/lib/jobs";
import PageHeader from "@/components/PageHeader";
import ScopeNote from "@/components/ScopeNote";
import Page from "@/components/Page";

export default async function RunPage() {
  const { data: catalog } = await getReplayCatalog();
  return <Page>
    <PageHeader eyebrow="Local historical replay" title="New run" aside={<Link href="/runs" className="button">Run history</Link>} />
    <ScopeNote>Replays a past market window on paper. The synthetic fixture only checks correctness. Queuing a run never starts data collection or trading.</ScopeNote>
    <RunForm catalog={catalog} />
  </Page>;
}
