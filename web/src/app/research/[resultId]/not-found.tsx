import Link from "next/link";
import ScopeNote from "@/components/ScopeNote";

export default function SavedResultNotFound() {
  return <main><h1>Saved result not found</h1><ScopeNote>This saved result is unavailable, outside this local operator’s scope, or no longer safely readable.</ScopeNote><Link className="button" href="/research">Back to saved research</Link></main>;
}
