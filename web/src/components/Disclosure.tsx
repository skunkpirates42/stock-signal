import type { ReactNode } from "react";

export interface DisclosureProps {
  summary: ReactNode;
  open?: boolean;
  className?: string;
  children?: ReactNode;
  onToggle?: (open: boolean) => void;
}

export default function Disclosure({
  summary,
  open,
  className,
  children,
  onToggle,
}: DisclosureProps) {
  return (
    <details
      open={open}
      className={className ? `disclosure ${className}` : "disclosure"}
      onToggle={onToggle && ((event) => onToggle(event.currentTarget.open))}
    >
      <summary>{summary}</summary>
      {children}
    </details>
  );
}
