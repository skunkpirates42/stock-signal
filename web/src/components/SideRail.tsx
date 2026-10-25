"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { isActiveRailLink } from "@/lib/navigation";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/signals", label: "Signals" },
  { href: "/positions", label: "Positions" },
  { href: "/research", label: "Research" },
  { href: "/run", label: "New run" },
  { href: "/runs", label: "Run history" },
  { href: "/system", label: "Design system" },
];

export default function SideRail() {
  const pathname = usePathname();
  const scope = useSearchParams().get("source") === "all" ? "all" : "live";
  const keepScope = (href: string) => (scope === "all" && ["/", "/signals", "/positions"].includes(href)
    ? `${href}?source=all` : href);

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
            className={`rail-link${isActiveRailLink(pathname, link.href) ? " rail-link-active" : ""}`}
            aria-current={isActiveRailLink(pathname, link.href) ? "page" : undefined}
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
            aria-current={scope === "live" ? "true" : undefined}
          >
            Live
          </Link>
          <Link
            href={`${pathname}?source=all`}
            className={`segmented-option${scope === "all" ? " segmented-option-active" : ""}`}
            aria-current={scope === "all" ? "true" : undefined}
          >
            All
          </Link>
        </div>
      </div>
    </aside>
  );
}
