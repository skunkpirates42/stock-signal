import Link from "next/link";

export default function RunNotFound() {
  return <main><h1>Run not found</h1><p className="scope-note">This run is unavailable, outside this local operator’s scope, or no longer safely readable.</p><Link className="button" href="/runs">Back to run history</Link></main>;
}
