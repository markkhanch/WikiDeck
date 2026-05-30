"""Tiny status / trigger icon loader for cards.

Icons live at:
    assets/icons/statuses/<STATUS_NAME>.png
    assets/icons/triggers/<TRIGGER_NAME>.png

Where <STATUS_NAME> is the uppercase status key (BLEEDING, POISON, SHIELD, ...).
Files should be square, transparent-background PNGs (game-icons.net style).
Missing files degrade gracefully — Card.draw falls back to a text label.
"""
from __future__ import annotations

import os
from typing import Optional

import pygame

_ICON_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets",
    "icons",
)

# Cache by (category, name, size) so we don't reload + rescale every frame.
_ICON_CACHE: dict[tuple[str, str, int], Optional[pygame.Surface]] = {}


# Statuses we want to surface as icons on the card front.
SUPPORTED_STATUSES: tuple[str, ...] = (
    "BLEEDING",
    "POISON",
    "SHIELD",
    "LOCK",
    "IMMUNITY",
    "DOOMED",
    "VEIL",
    "TIMER",
    "VITALITY",
)


def _load(category: str, name: str, size: int) -> Optional[pygame.Surface]:
    key = (category, name, size)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    path = os.path.join(_ICON_DIR, category, f"{name}.png")
    if not os.path.isfile(path):
        _ICON_CACHE[key] = None
        return None
    try:
        raw = pygame.image.load(path)
        try:
            raw = raw.convert_alpha()
        except pygame.error:
            pass
        scaled = pygame.transform.smoothscale(raw, (size, size))
        _ICON_CACHE[key] = scaled
        return scaled
    except pygame.error:
        _ICON_CACHE[key] = None
        return None


def get_status_icon(status: str, size: int = 12) -> Optional[pygame.Surface]:
    """Load and scale a status icon. Returns None if file missing or load failed."""
    return _load("statuses", status.upper(), size)


def get_trigger_icon(trigger: str, size: int = 12) -> Optional[pygame.Surface]:
    """Load and scale a trigger icon. Returns None if file missing."""
    return _load("triggers", trigger.upper(), size)
