import Link from "next/link";
import ScopeNote from "@/components/ScopeNote";
import Page from "@/components/Page";

export default function RunNotFound() {
  return <Page><h1>Run not found</h1><ScopeNote>This run doesn’t exist or can’t be opened here.</ScopeNote><Link className="button" href="/runs">Back to run history</Link></Page>;
}
