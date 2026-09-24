import Link from "next/link";
import RunForm from "@/components/RunForm";
import { getReplayCatalog } from "@/lib/jobs";

export default async function RunPage() {
  const { data: catalog } = await getReplayCatalog();
  return <main>
    <div className="page-head"><div><h1>New run</h1><p className="micro">Local historical replay</p></div><Link href="/runs" className="button">Run history</Link></div>
    <p className="scope-note">Paper-only historical simulation. Market windows are retrospective; the synthetic fixture checks correctness only. Submitting a run does not activate collection or trading.</p>
    <RunForm catalog={catalog} />
  </main>;
}
