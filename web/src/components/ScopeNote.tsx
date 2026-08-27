import type { ReactNode } from "react";

export interface ScopeNoteProps {
  children: ReactNode;
}

export default function ScopeNote({ children }: ScopeNoteProps) {
  return (
    <div className="scope-note">
      <p>{children}</p>
    </div>
  );
}
