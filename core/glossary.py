"""Glossary of WikiDeck game terms — triggers, effects, statuses.

Single source of truth so the hover popup, the full-card detail modal, and
the deckbuilder all explain terms the same way.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.card import Card


# term -> one-line plain-English definition (player-facing, not engine speak).
TERM_DEFINITIONS: dict[str, str] = {
    # ----- Triggers -----
    "DEPLOY": "Fires once when this card is played from your hand.",
    "ORDER": "Click the card to activate. One use per game; doesn't spend your main action.",
    "ORDER_ZEAL": "Click the card to activate. One use per game; doesn't spend your main action.",
    "DEATHWISH": "Fires when this card dies.",
    "DEATHBLOW": "Fires when this card destroys an enemy card.",
    "ON DEATH:ALLY": "Fires whenever any of your other cards dies.",
    "ON DEATH:ENEMY": "Fires whenever any enemy card dies.",
    "TIMER": "Counts down at the end of each turn; ability fires when it reaches zero.",
    "ADRENALINE": "Fires automatically while your hand is small enough.",
    "BLOODTHIRST": "Fires automatically once you've made enough kills this game.",
    "PASSIVE": "Continuous effect while this card is on the field.",
    "END OF TURN": "Fires at the end of every turn.",
    "START OF TURN": "Fires at the start of every turn.",
    "NO ABILITY": "This card has no active ability — pure stats.",

    # ----- Effects / statuses (same name often used for both) -----
    "DAMAGE":   "Lower a target card's HP by the listed amount.",
    "DESTROY":  "Kill a target card outright and send it to discard.",
    "BANISH":   "Remove a target card from the field without sending it to discard (cannot be revived).",
    "HEAL":     "Restore a card to its full HP.",
    "BLEEDING": "Bleeding cards lose 1 HP at the end of each of their turns. Stacks count down.",
    "POISON":   "A card with 2 stacks of Poison dies at end of turn.",
    "VITALITY": "Vitality cards gain 1 HP at the end of each of their turns. Stacks count down.",
    "SHIELD":   "Blocks the next incoming damage instance, then disappears.",
    "IMMUNITY": "While Immunity is active, the card cannot be targeted by any ability.",
    "LOCK":     "Locked cards cannot use their abilities.",
    "VEIL":     "Veiled cards cannot be chosen as targets by enemy abilities.",
    "DOOMED":   "When this card dies, it is removed entirely instead of going to discard.",
    "DUEL":     "Two cards trade damage equal to their HP, back and forth, until one dies.",
    "CLASH":    "Two cards deal damage to each other simultaneously, equal to their current HP.",
    "DRAW":     "Draw cards from your deck into your hand.",
    "DISCARD":  "The enemy randomly discards cards from their hand.",
    "REVIVE":   "Return one card from your discard pile back onto your field.",
}


def _normalize(name: str | None) -> str:
    return str(name or "").strip().upper()


def terms_used_by_card(card: "Card") -> list[str]:
    """Return de-duplicated, ordered list of glossary terms relevant to this card.

    Order is intentional: trigger first, then effect, then any active statuses.
    Only terms we have definitions for are returned.
    """
    seen: set[str] = set()
    ordered: list[str] = []

    def _add(term: str) -> None:
        norm = _normalize(term)
        if not norm or norm in seen:
            return
        if norm not in TERM_DEFINITIONS:
            return
        seen.add(norm)
        ordered.append(norm)

    _add(getattr(card, "ability_trigger", ""))
    _add(getattr(card, "effect_type", ""))

    statuses = getattr(card, "statuses", None) or {}
    if isinstance(statuses, dict):
        for status_name, value in statuses.items():
            if isinstance(value, bool):
                if not value:
                    continue
            else:
                try:
                    if int(value) <= 0:
                        continue
                except Exception:
                    continue
            _add(status_name)

    return ordered


def glossary_for_card(card: "Card") -> list[tuple[str, str]]:
    """List of (TERM, definition) pairs to show in the card detail modal."""
    return [(term, TERM_DEFINITIONS[term]) for term in terms_used_by_card(card)]


def active_status_labels(card: "Card") -> list[str]:
    """Player-facing labels for currently-active statuses on the card.

    Example: ["BLEEDING (3)", "SHIELD"]. Returned in the order statuses
    appear in the dict (stable). Empty list if no statuses are active.
    """
    statuses = getattr(card, "statuses", None) or {}
    if not isinstance(statuses, dict):
        return []
    out: list[str] = []
    for name, value in statuses.items():
        label = str(name).strip().upper()
        if not label:
            continue
        if isinstance(value, bool):
            if value:
                out.append(label)
            continue
        try:
            count = int(value)
        except Exception:
            count = 0
        if count > 1:
            out.append(f"{label} ({count})")
        elif count == 1:
            out.append(label)
    if int(getattr(card, "silenced_turns", 0) or 0) > 0 and "LOCK" not in (s.split(" ")[0] for s in out):
        out.append("LOCK")
    return out
