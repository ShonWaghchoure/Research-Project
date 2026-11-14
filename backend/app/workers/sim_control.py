"""Runtime controls for the live market simulation (admin start/stop/speed).

Flags never touch the chain; they only gate the clock tick and override interval length.
Defaults match settings at process start. Changes are process-local (not persisted).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional

from app.core.config import settings


@dataclass
class SimControlState:
    running: bool = True
    interval_seconds: Optional[int] = None  # None → use settings.INTERVAL_SECONDS


_lock = threading.Lock()
_state = SimControlState()


def get_state() -> dict[str, object]:
    with _lock:
        secs = _state.interval_seconds if _state.interval_seconds is not None else int(settings.INTERVAL_SECONDS)
        return {
            "running": _state.running,
            "interval_seconds": secs,
            "override_active": _state.interval_seconds is not None,
        }


def start() -> dict[str, object]:
    with _lock:
        _state.running = True
    return get_state()


def stop() -> dict[str, object]:
    with _lock:
        _state.running = False
    return get_state()


def set_speed(interval_seconds: int) -> dict[str, object]:
    if interval_seconds < 5 or interval_seconds > 3600:
        raise ValueError("interval_seconds must be between 5 and 3600")
    with _lock:
        _state.interval_seconds = int(interval_seconds)
    return get_state()


def is_running() -> bool:
    with _lock:
        return _state.running


def interval_seconds() -> int:
    with _lock:
        if _state.interval_seconds is not None:
            return int(_state.interval_seconds)
    return int(settings.INTERVAL_SECONDS)
