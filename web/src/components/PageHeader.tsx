import Link from "next/link";
import type { ReactNode } from "react";

export interface PageHeaderProps {
  title: ReactNode;
  eyebrow?: ReactNode;
  aside?: ReactNode;
  back?: { href: string; label: string };
}

export default function PageHeader({ title, eyebrow, aside, back }: PageHeaderProps) {
  return (
    <>
      {back && (
        <Link className="micro page-back" href={back.href}>
          ← {back.label}
        </Link>
      )}
      <div className="page-head">
        <div>
          {eyebrow && <p className="micro">{eyebrow}</p>}
          <h1>{title}</h1>
        </div>
        {aside}
      </div>
    </>
  );
}
