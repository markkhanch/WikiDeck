"""Shared, thread-safe Ollama health check state.

Used by the main menu (status badge) and the shop (decides whether to even
attempt LLM-backed generation messaging). A single background worker pings
candidate hosts and updates the cached state; UI just reads it each frame.
"""
from __future__ import annotations

import threading
import time
from typing import Optional


# status:
#   "unknown"   — never checked yet
#   "checking"  — background check in progress
#   "online"    — at least one host responded
#   "offline"   — every host failed / Ollama disabled
_STATE: dict[str, object] = {
    "status": "unknown",
    "host": None,
    "message": "Checking AI…",
    "checked_at": 0.0,
}
_LOCK = threading.Lock()
_CHECK_IN_FLIGHT = False


def _set(status: str, host: Optional[str], message: str) -> None:
    changed = False
    with _LOCK:
        if _STATE.get("status") != status or _STATE.get("message") != message:
            changed = True
        _STATE["status"] = status
        _STATE["host"] = host
        _STATE["message"] = message
        _STATE["checked_at"] = time.time()
    if changed:
        marker = {"online": "✓", "offline": "✗", "checking": "…", "unknown": "?"}.get(status, "·")
        print(f"[ai-health] {marker} {message}", flush=True)


def get_state() -> dict:
    """Read a snapshot of the current state. Safe to call every frame."""
    with _LOCK:
        return dict(_STATE)


def _background_worker() -> None:
    global _CHECK_IN_FLIGHT
    _set("checking", None, "Checking AI…")
    try:
        try:
            from data.settings_service import get_bool
            if not get_bool("ai.use_ollama"):
                _set("offline", None, "AI disabled (template mode)")
                return
        except Exception:
            pass

        try:
            from data.ollama_gen_v2 import _host_candidates, _ping_ollama
        except Exception as exc:
            _set("offline", None, f"AI module unavailable: {exc}")
            return

        for host in _host_candidates():
            try:
                if _ping_ollama(host):
                    _set("online", host, f"AI online · {host}")
                    return
            except Exception:
                continue
        _set("offline", None, "AI offline — template mode")
    finally:
        with _LOCK:
            _CHECK_IN_FLIGHT = False


def kick_check(force: bool = False) -> None:
    """Start a background ping. No-op if one is already in flight.

    The check is non-blocking — the caller can render the menu immediately
    and the badge will swap as soon as the worker finishes.
    """
    global _CHECK_IN_FLIGHT
    with _LOCK:
        if _CHECK_IN_FLIGHT and not force:
            return
        _CHECK_IN_FLIGHT = True
    threading.Thread(target=_background_worker, daemon=True).start()
