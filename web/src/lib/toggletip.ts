export interface ToggletipState {
  open: boolean;
  pinned: boolean;
}

export type ToggletipEvent = "hover" | "unhover" | "focus" | "blur" | "toggle" | "dismiss";

export const CLOSED: ToggletipState = { open: false, pinned: false };

export function nextToggletipState(state: ToggletipState, event: ToggletipEvent): ToggletipState {
  switch (event) {
    case "hover":
    case "focus":
      return { open: true, pinned: state.pinned };
    case "unhover":
      return state.pinned ? state : CLOSED;
    case "toggle":
      return state.pinned ? CLOSED : { open: true, pinned: true };
    case "blur":
    case "dismiss":
      return CLOSED;
  }
}

const VIEWPORT_GUTTER = 16;

export function toggletipPosition(
  anchor: { top: number; bottom: number; left: number },
  panel: { width: number; height: number },
  viewport: { width: number; height: number },
) {
  const fitsBelow = anchor.bottom + panel.height <= viewport.height - VIEWPORT_GUTTER;
  const top = fitsBelow ? anchor.bottom : anchor.top - panel.height;
  const rightmostLeft = viewport.width - VIEWPORT_GUTTER - panel.width;
  const left = Math.max(VIEWPORT_GUTTER, Math.min(anchor.left, rightmostLeft));
  return { top, left };
}
