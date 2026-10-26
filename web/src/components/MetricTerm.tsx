"use client";

import { useEffect, useId, useLayoutEffect, useReducer, useRef } from "react";
import type { MetricDefinition } from "@/lib/metricDefinitions";
import { CLOSED, nextToggletipState, toggletipPosition } from "@/lib/toggletip";

export default function MetricTerm({ term, meaning, formula }: MetricDefinition) {
  const [state, dispatch] = useReducer(nextToggletipState, CLOSED);
  const wrapperRef = useRef<HTMLSpanElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLSpanElement>(null);
  const panelId = useId();

  useLayoutEffect(() => {
    const button = buttonRef.current;
    const panel = panelRef.current;
    if (!button || !panel) return;
    const isShown = panel.matches(":popover-open");
    if (!state.open) {
      if (isShown) panel.hidePopover();
      return;
    }
    if (!isShown) panel.showPopover();
    const { top, left } = toggletipPosition(
      button.getBoundingClientRect(),
      panel.getBoundingClientRect(),
      { width: window.innerWidth, height: window.innerHeight },
    );
    panel.style.top = `${top}px`;
    panel.style.left = `${left}px`;
  }, [state.open]);

  useEffect(() => {
    if (!state.open) return;
    const dismiss = () => dispatch("dismiss");
    const dismissOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") dismiss();
    };
    const dismissOnOutsidePointer = (event: PointerEvent) => {
      if (!wrapperRef.current?.contains(event.target as Node)) dismiss();
    };
    document.addEventListener("keydown", dismissOnEscape);
    document.addEventListener("pointerdown", dismissOnOutsidePointer);
    window.addEventListener("scroll", dismiss, { capture: true, passive: true });
    window.addEventListener("resize", dismiss);
    return () => {
      document.removeEventListener("keydown", dismissOnEscape);
      document.removeEventListener("pointerdown", dismissOnOutsidePointer);
      window.removeEventListener("scroll", dismiss, { capture: true });
      window.removeEventListener("resize", dismiss);
    };
  }, [state.open]);

  return (
    <span
      ref={wrapperRef}
      className="metric-term"
      onPointerEnter={() => dispatch("hover")}
      onPointerLeave={() => dispatch("unhover")}
    >
      <button
        ref={buttonRef}
        type="button"
        className="metric-term-trigger"
        aria-expanded={state.open}
        aria-controls={panelId}
        onFocus={() => dispatch("focus")}
        onBlur={() => dispatch("blur")}
        onClick={() => dispatch("toggle")}
      >
        {term}
      </button>
      <span
        ref={panelRef}
        id={panelId}
        popover="manual"
        className="metric-term-popover"
        onMouseDown={(event) => event.preventDefault()}
      >
        <span className="metric-term-panel">
          <span className="metric-term-meaning">{meaning}</span>
          <span className="metric-term-formula num">{formula}</span>
        </span>
      </span>
    </span>
  );
}
