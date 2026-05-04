"""Combo detection (GDD §5.3)."""
from typing import Dict, List, Tuple

from core.card import Card


def confluence_bonus(field_cards: List[Card]) -> float:
    """+0.3x per card over 2 in any theme that has 3+ on the field."""
    counts: Dict[str, int] = {}
    for c in field_cards:
        theme = str(getattr(c, "theme", "") or "")
        counts[theme] = counts.get(theme, 0) + 1
    bonus = 0.0
    for count in counts.values():
        if count >= 3:
            bonus += 0.3 * (count - 2)
    return bonus


def epoch_bonus(field_cards: List[Card]) -> float:
    """+0.4x per group of 3 cards in the same epoch."""
    counts: Dict[str, int] = {}
    for c in field_cards:
        epoch = str(getattr(c, "epoch", "TIMELESS") or "TIMELESS").upper()
        counts[epoch] = counts.get(epoch, 0) + 1
    bonus = 0.0
    for count in counts.values():
        bonus += 0.4 * (count // 3)
    return bonus


def nemesis_bonus(field_cards: List[Card]) -> float:
    """+1.5x for each active nemesis pair on field."""
    bonus = 0.0
    for i, left in enumerate(field_cards):
        left_title = str(getattr(left, "title", "") or "").strip()
        left_nemesis = str(getattr(left, "nemesis", "") or "").strip()
        for right in field_cards[i + 1 :]:
            right_title = str(getattr(right, "title", "") or "").strip()
            right_nemesis = str(getattr(right, "nemesis", "") or "").strip()
            if not left_title or not right_title:
                continue
            if left_nemesis == right_title or right_nemesis == left_title:
                bonus += 1.5
    return bonus


def graveyard_bonus(graveyard_eligible_count: int) -> float:
    """+0.1x per 3 qualifying cards in discard."""
    return 0.1 * (max(0, int(graveyard_eligible_count)) // 3)


def legend_bonus(field_cards: List[Card]) -> float:
    """+0.2x if at least one LEGENDARY is alive on field."""
    if any(str(getattr(c, "rarity", "") or "").upper() == "LEGENDARY" for c in field_cards):
        return 0.2
    return 0.0


def active_combos(
    field_cards: List[Card],
    *,
    graveyard_eligible_count: int = 0,
    hyperlink_bonus_value: float = 0.0,
) -> List[Tuple[str, float]]:
    """List of (combo_name, bonus) currently active. Empty if none."""
    result: List[Tuple[str, float]] = []
    hyperlink = float(hyperlink_bonus_value)
    confluence = confluence_bonus(field_cards)
    epoch = epoch_bonus(field_cards)
    nemesis = nemesis_bonus(field_cards)
    graveyard = graveyard_bonus(graveyard_eligible_count)
    legend = legend_bonus(field_cards)
    if hyperlink > 0:
        result.append(("HYPERLINK", hyperlink))
    if confluence > 0:
        result.append(("CONFLUENCE", confluence))
    if epoch > 0:
        result.append(("EPOCH", epoch))
    if nemesis > 0:
        result.append(("NEMESIS", nemesis))
    if graveyard > 0:
        result.append(("GRAVEYARD", graveyard))
    if legend > 0:
        result.append(("LEGEND", legend))
    return result


def multiplier(
    field_cards: List[Card],
    *,
    graveyard_eligible_count: int = 0,
    hyperlink_bonus_value: float = 0.0,
) -> float:
    """Total multiplier from all active combos. Base is 1.0 (GDD §5.2)."""
    return 1.0 + sum(
        bonus
        for _, bonus in active_combos(
            field_cards,
            graveyard_eligible_count=graveyard_eligible_count,
            hyperlink_bonus_value=hyperlink_bonus_value,
        )
    )
