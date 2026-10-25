import Link from "next/link";
import ScopeNote from "@/components/ScopeNote";

export default function RunNotFound() {
  return <main><h1>Run not found</h1><ScopeNote>This run is unavailable, outside this local operator’s scope, or no longer safely readable.</ScopeNote><Link className="button" href="/runs">Back to run history</Link></main>;
}
