"""Combo detection (GDD §5.3).

MVP: only CONFLUENCE is implemented. HYPERLINK / EPOCH / NEMESIS /
GRAVEYARD / LEGEND come later once we have epoch/nemesis data per card
and a working discard pile distinction.
"""
from typing import Dict, List, Tuple

from core.card import Card


# ---- individual combos ----

def confluence_bonus(field_cards: List[Card]) -> float:
    """+0.3x per card over 2 in any theme that has 3+ on the field.

    Example: 3 SCIENCE cards → +0.3x. 5 SCIENCE → +0.9x. 3 SCIENCE + 3 LIVING → +0.6x.
    """
    counts: Dict[str, int] = {}
    for c in field_cards:
        counts[c.theme] = counts.get(c.theme, 0) + 1
    bonus = 0.0
    for count in counts.values():
        if count >= 3:
            bonus += 0.3 * (count - 2)
    return bonus


# ---- aggregates used by the UI / scoring ----

def active_combos(field_cards: List[Card]) -> List[Tuple[str, float]]:
    """List of (combo_name, bonus) currently active. Empty if none."""
    result: List[Tuple[str, float]] = []
    cb = confluence_bonus(field_cards)
    if cb > 0:
        result.append(("CONFLUENCE", cb))
    return result


def multiplier(field_cards: List[Card]) -> float:
    """Total multiplier from all active combos. Base is 1.0 (GDD §5.2)."""
    return 1.0 + confluence_bonus(field_cards)
