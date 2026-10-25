import Link from "next/link";
import ScopeNote from "@/components/ScopeNote";

export default function SavedResultNotFound() {
  return <main><h1>Saved result not found</h1><ScopeNote>This saved result doesn’t exist or can’t be opened here.</ScopeNote><Link className="button" href="/research">Back to saved research</Link></main>;
}
