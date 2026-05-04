"""Trigger dispatch and status ticks for match runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from core.effects import Effect, apply_effect

if TYPE_CHECKING:
    from core.card import Card
    from core.game_state import GameState
    from core.player import Player


def normalize_trigger_name(value: str) -> str:
    return str(value or "").strip().upper()


def _normalized_trigger(card: "Card") -> str:
    trigger = normalize_trigger_name(str(getattr(card, "ability_trigger", "") or ""))
    if trigger:
        return trigger
    on_play = getattr(card, "on_play", Effect.NONE)
    on_death = getattr(card, "on_death", Effect.NONE)
    if on_play != Effect.NONE:
        return "DEPLOY"
    if on_death != Effect.NONE:
        return "DEATHWISH"
    return "NO ABILITY"


def _debug(game_state: "GameState", message: str, *, include_state: bool = False) -> None:
    if hasattr(game_state, "debug"):
        game_state.debug(message, include_state=include_state)


def fire_triggers(
    trigger_type: str,
    game_state: "GameState",
    owner: "Player",
    source_card: Optional["Card"] = None,
) -> None:
    """Apply all effects on owner field that match trigger_type."""
    source_name = source_card.title if source_card is not None else "-"
    normalized = normalize_trigger_name(trigger_type)
    cards = list(owner.on_field)
    if normalized == "DEPLOY":
        cards = [source_card] if source_card in owner.on_field else []
    if game_state.is_targeting_active():
        _debug(game_state, f"TRIGGER deferred type={normalized} because targeting is active.")
        for queued in cards:
            if _normalized_trigger(queued) == normalized and getattr(queued, "silenced_turns", 0) <= 0:
                game_state.queue_pending_effect(queued, owner)
        return
    _debug(
        game_state,
        f"TRIGGER fire type={normalized} owner={owner.name} source={source_name} field_cards={len(owner.on_field)}",
    )
    for idx, card in enumerate(cards):
        if card not in owner.on_field:
            _debug(game_state, f"TRIGGER skip removed card={card.title}.")
            continue
        card_trigger = _normalized_trigger(card)
        if card_trigger != normalized:
            continue
        if getattr(card, "silenced_turns", 0) > 0:
            _debug(game_state, f"TRIGGER skip {card.title}: silenced_turns={card.silenced_turns}.")
            continue
        _debug(game_state, f"TRIGGER apply {card.title} for {normalized}.")
        msg = apply_effect(card, game_state, owner)
        if msg:
            game_state.log_event(msg)
        else:
            _debug(game_state, f"TRIGGER no-op for {card.title}.")
        if game_state.is_targeting_active():
            _debug(game_state, f"TRIGGER paused due to targeting request by {card.title}.")
            for queued in cards[idx + 1 :]:
                if queued in owner.on_field and _normalized_trigger(queued) == normalized and getattr(queued, "silenced_turns", 0) <= 0:
                    game_state.queue_pending_effect(queued, owner)
            break


def _status_count(card: "Card", status: str) -> int:
    raw = getattr(card, "statuses", {}) or {}
    if isinstance(raw, dict):
        value = raw.get(status, 0)
        if isinstance(value, bool):
            return 1 if value else 0
        try:
            return max(0, int(value))
        except Exception:
            return 0
    if isinstance(raw, (set, list, tuple)):
        return 1 if status in raw else 0
    return 0


def _set_status(card: "Card", status: str, value: int | bool) -> None:
    raw = getattr(card, "statuses", {})
    if not isinstance(raw, dict):
        if isinstance(raw, (set, list, tuple)):
            raw = {str(name).upper(): 1 for name in raw}
        else:
            raw = {}
        card.statuses = raw
    if isinstance(value, bool):
        if value:
            raw[status] = True
        else:
            raw.pop(status, None)
        return
    if int(value) > 0:
        raw[status] = int(value)
    else:
        raw.pop(status, None)


def apply_status_ticks(game_state: "GameState", owner: "Player") -> None:
    _debug(game_state, f"STATUS ticks owner={owner.name} field_cards={len(owner.on_field)}")
    for card in list(owner.on_field):
        if card not in owner.on_field:
            continue

        # BLEEDING - deal 1 damage at end of turn and decrement stack.
        bleeding = _status_count(card, "BLEEDING")
        if bleeding > 0:
            card.hp -= 1
            _set_status(card, "BLEEDING", bleeding - 1)
            if card.hp <= 0:
                game_state.kill_card(owner, card)
                continue

        # VITALITY - heal 1 at end of turn and decrement stack.
        vitality = _status_count(card, "VITALITY")
        if vitality > 0:
            card.hp = min(card.hp + 1, max(1, int(getattr(card, "max_hp", card.hp))))
            _set_status(card, "VITALITY", vitality - 1)

        # POISON - destroy at 2+ stacks.
        if _status_count(card, "POISON") >= 2:
            game_state.kill_card(owner, card)
            continue

        # TIMER - countdown and fire card effect at zero.
        timer = _status_count(card, "TIMER")
        if timer > 0:
            _set_status(card, "TIMER", timer - 1)
            if timer - 1 == 0:
                msg = apply_effect(card, game_state, owner)
                if msg:
                    game_state.log_event(msg)

        # LOCK is permanent here, no tick-down.
