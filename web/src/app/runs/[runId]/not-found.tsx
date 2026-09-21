import Link from "next/link";

export default function SavedResultNotFound() {
  return <main><h1>Saved result not found</h1><p className="scope-note">This saved result is unavailable, outside this local operator’s scope, or no longer safely readable.</p><Link className="button" href="/research">Back to saved research</Link></main>;
}
