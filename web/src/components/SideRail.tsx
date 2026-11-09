"use client";

import IntentPrefetchLink from "@/components/IntentPrefetchLink";
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
  const searchParams = useSearchParams();
  const scope = searchParams.get("source") === "all" ? "all" : "live";
  const scopeHref = (source: "live" | "all") => {
    const params = new URLSearchParams(pathname === "/signals" ? searchParams.toString() : "");
    params.delete("page");
    params.delete("snapshot_id");
    if (source === "all") params.set("source", "all");
    else params.delete("source");
    return params.size ? `${pathname}?${params}` : pathname;
  };
  const keepScope = (href: string) =>
    scope === "all" && ["/", "/signals", "/positions"].includes(href) ? `${href}?source=all` : href;

  return (
    <aside className="rail">
      <IntentPrefetchLink href={keepScope("/")} className="rail-mark">
        PT<span className="rail-mark-slash">{"//"}</span>26
      </IntentPrefetchLink>

      <nav className="rail-nav" aria-label="Primary">
        {LINKS.map((link) => (
          <IntentPrefetchLink
            key={link.href}
            href={keepScope(link.href)}
            className={`rail-link${isActiveRailLink(pathname, link.href) ? " rail-link-active" : ""}`}
            aria-current={isActiveRailLink(pathname, link.href) ? "page" : undefined}
          >
            {link.label}
          </IntentPrefetchLink>
        ))}
      </nav>

      <div className="rail-scope">
        <span className="micro">Scope</span>
        <div className="segmented">
          <IntentPrefetchLink
            href={scopeHref("live")}
            className={`segmented-option${scope === "live" ? " segmented-option-active" : ""}`}
            aria-current={scope === "live" ? "true" : undefined}
          >
            Live
          </IntentPrefetchLink>
          <IntentPrefetchLink
            href={scopeHref("all")}
            className={`segmented-option${scope === "all" ? " segmented-option-active" : ""}`}
            aria-current={scope === "all" ? "true" : undefined}
          >
            All
          </IntentPrefetchLink>
        </div>
      </div>
    </aside>
  );
}
