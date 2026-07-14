"""Native desktop notifications.

Fires a macOS Notification Center banner via the built-in `osascript` (no third-party
dependency, no bot token). Wired into `run_live.py`'s `on_event` hook, so you get pinged
the moment a signal/open/close happens even with no browser tab open — which is the point
of moving off Telegram for personal use.

Everything here is best-effort: off macOS, or if osascript fails, it silently no-ops so
the trading loop never breaks over a notification.
"""

import platform
import subprocess

import config

ACTIONABLE = ("LONG", "SHORT")


def _escape(s) -> str:
    """Escape a value for an AppleScript double-quoted string literal."""
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def notify(title: str, body: str, subtitle: str = None, sound: str = None) -> bool:
    """Show a native macOS notification. Returns True if dispatched, False if skipped/failed."""
    if platform.system() != "Darwin":
        return False
    script = f'display notification "{_escape(body)}" with title "{_escape(title)}"'
    if subtitle:
        script += f' subtitle "{_escape(subtitle)}"'
    if sound:
        script += f' sound name "{_escape(sound)}"'
    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return True
    except Exception:
        return False


def format_event(kind: str, payload: dict):
    """Return (title, subtitle, body) strings for a live on_event payload."""
    tkr = payload.get("ticker")
    if kind == "signal":
        conf = round((payload.get("confidence") or 0) * 100)
        return (
            f"{tkr} {payload.get('direction')}",
            f"confidence {conf}%",
            f"entry {payload.get('entry')} · stop {payload.get('stop')} · "
            f"target {payload.get('target')} · R:R {payload.get('rr')}",
        )
    if kind == "open":
        return (
            f"{tkr} opened",
            payload.get("direction"),
            f"{payload.get('shares')} sh @ {payload.get('entry')}",
        )
    if kind == "close":
        pnl = payload.get("pnl") or 0.0
        return (
            f"{tkr} {payload.get('outcome')}",
            f"P&L {pnl:+.2f}",
            f"exit {payload.get('exit_price')} · {payload.get('bars_held')} bars",
        )
    return (str(tkr), kind, "")


def notify_event(kind: str, payload: dict, min_confidence: float = None) -> bool:
    """Notify for a signal/open/close event, honoring the min-confidence gate for signals."""
    if min_confidence is None:
        min_confidence = config.ALERT_MIN_CONFIDENCE

    if kind == "signal":
        if payload.get("direction") not in ACTIONABLE:
            return False  # WAIT signals aren't alerts
        if (payload.get("confidence") or 0) < min_confidence:
            return False
    elif kind not in ("open", "close"):
        return False

    title, subtitle, body = format_event(kind, payload)
    return notify(title, body, subtitle=subtitle, sound=config.ALERT_SOUND or None)
