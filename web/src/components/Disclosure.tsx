import type { ReactNode } from "react";

export interface DisclosureProps {
  summary: ReactNode;
  className?: string;
  children?: ReactNode;
}

export default function Disclosure({ summary, className, children }: DisclosureProps) {
  return <details className={className ? `disclosure ${className}` : "disclosure"}>
    <summary>{summary}</summary>
    {children}
  </details>;
}
