import type { ReactNode } from "react";

export interface PageProps {
  className?: string;
  children?: ReactNode;
}

export default function Page({ className, children }: PageProps) {
  return <main className={className}>{children}</main>;
}
