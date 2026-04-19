"""Trigger dispatch and status ticks for match runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from core.effects import Effect, apply_effect

if TYPE_CHECKING:
    from core.card import Card
    from core.game_state import GameState
    from core.player import Player


def _normalized_trigger(card: "Card") -> str:
    trigger = str(getattr(card, "ability_trigger", "") or "").strip().upper()
    if trigger:
        return trigger
    on_play = getattr(card, "on_play", Effect.NONE)
    on_death = getattr(card, "on_death", Effect.NONE)
    if on_play != Effect.NONE:
        return "ON PLAY"
    if on_death != Effect.NONE:
        return "ON DEATH:SELF"
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
    normalized = trigger_type.strip().upper()
    if game_state.is_targeting_active():
        _debug(game_state, f"TRIGGER deferred type={normalized} because targeting is active.")
        for queued in list(owner.on_field):
            if _normalized_trigger(queued) == normalized and getattr(queued, "silenced_turns", 0) <= 0:
                game_state.queue_pending_effect(queued, owner)
        return
    _debug(
        game_state,
        f"TRIGGER fire type={normalized} owner={owner.name} source={source_name} field_cards={len(owner.on_field)}",
    )
    cards = list(owner.on_field)
    for idx, card in enumerate(cards):
        if card not in owner.on_field:
            _debug(game_state, f"TRIGGER skip removed card={card.title}.")
            continue
        card_trigger = _normalized_trigger(card)
        if card_trigger != normalized:
            _debug(game_state, f"TRIGGER skip {card.title}: trigger={card_trigger} != {normalized}.")
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


def apply_status_ticks(game_state: "GameState", owner: "Player") -> None:
    _debug(game_state, f"STATUS ticks owner={owner.name} field_cards={len(owner.on_field)}")
    for card in list(owner.on_field):
        if card not in owner.on_field:
            _debug(game_state, f"STATUS skip removed card={card.title}.")
            continue

        raw_statuses = getattr(card, "statuses", set())
        if isinstance(raw_statuses, list):
            card.statuses = set(raw_statuses)
        elif isinstance(raw_statuses, set):
            card.statuses = raw_statuses
        else:
            card.statuses = set()
        statuses = set(card.statuses)
        _debug(game_state, f"STATUS card={card.title} statuses={sorted(statuses)} hp={card.hp} sc={card.base_score}")
        if "PLAGUE" in statuses:
            before = card.hp
            card.hp -= 1
            _debug(game_state, f"STATUS PLAGUE {card.title} hp {before}->{card.hp}")
            if card.hp <= 0:
                game_state.log_event(f"{card.title}: PLAGUE deals 1 damage.")
                game_state.kill_card(owner, card)
                continue
        if "VIGOR" in statuses:
            before = card.hp
            card.hp = min(card.hp + 1, max(1, int(getattr(card, "max_hp", card.hp))))
            _debug(game_state, f"STATUS VIGOR {card.title} hp {before}->{card.hp}")
        if "DECAY" in statuses:
            before = card.base_score
            card.base_score = max(0, card.base_score - 1)
            _debug(game_state, f"STATUS DECAY {card.title} sc {before}->{card.base_score}")
        if "FLOURISH" in statuses:
            before = card.base_score
            card.base_score += 1
            _debug(game_state, f"STATUS FLOURISH {card.title} sc {before}->{card.base_score}")
        if getattr(card, "silenced_turns", 0) > 0:
            before = card.silenced_turns
            card.silenced_turns -= 1
            _debug(game_state, f"STATUS SILENCE {card.title} turns {before}->{card.silenced_turns}")
