"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/signals", label: "Signals" },
  { href: "/positions", label: "Positions" },
];

export default function SideRail() {
  const pathname = usePathname();
  const scope = useSearchParams().get("source") === "all" ? "all" : "live";
  const keepScope = (href: string) => (scope === "all" ? `${href}?source=all` : href);

  return (
    <aside className="rail">
      <Link href={keepScope("/")} className="rail-mark">
        PT<span className="rail-mark-slash">{"//"}</span>26
      </Link>

      <nav className="rail-nav" aria-label="Primary">
        {LINKS.map((link) => (
          <Link
            key={link.href}
            href={keepScope(link.href)}
            className={`rail-link${pathname === link.href ? " rail-link-active" : ""}`}
            aria-current={pathname === link.href ? "page" : undefined}
          >
            {link.label}
          </Link>
        ))}
      </nav>

      <div className="rail-scope">
        <span className="micro">Scope</span>
        <div className="segmented">
          <Link
            href={pathname}
            className={`segmented-option${scope === "live" ? " segmented-option-active" : ""}`}
          >
            Live
          </Link>
          <Link
            href={`${pathname}?source=all`}
            className={`segmented-option${scope === "all" ? " segmented-option-active" : ""}`}
          >
            All
          </Link>
        </div>
      </div>
    </aside>
  );
}
