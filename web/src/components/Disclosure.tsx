import type { ReactNode } from "react";

export interface DisclosureProps {
  summary: ReactNode;
  open?: boolean;
  className?: string;
  children?: ReactNode;
}

export default function Disclosure({ summary, open, className, children }: DisclosureProps) {
  return <details open={open} className={className ? `disclosure ${className}` : "disclosure"}>
    <summary>{summary}</summary>
    {children}
  </details>;
}
