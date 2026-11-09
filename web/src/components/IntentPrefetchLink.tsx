"use client";

import Link from "next/link";
import { useState, type ComponentProps } from "react";

// Always-visible navigation would otherwise re-prefetch every dynamic route after each
// router.refresh(); prefetching on hover, focus or touch keeps instant loading states.
export default function IntentPrefetchLink(props: Omit<ComponentProps<typeof Link>, "prefetch">) {
  const [showsIntent, setShowsIntent] = useState(false);
  const markIntent = () => setShowsIntent(true);
  return (
    <Link
      {...props}
      prefetch={showsIntent ? null : false}
      onMouseEnter={markIntent}
      onFocus={markIntent}
      onTouchStart={markIntent}
    />
  );
}
