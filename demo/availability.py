"""A1 availability objects: a value with its evidence state, never a bare null or 0."""
from __future__ import annotations

from typing import Any, Dict, Optional


def available(value: Any, detail: Optional[str] = None) -> Dict[str, Any]:
    return {"availability": "available", "value": value, "reason": None, "detail": detail}


def unavailable(reason: str, detail: str) -> Dict[str, Any]:
    return {"availability": "unavailable", "value": None, "reason": reason, "detail": detail}
