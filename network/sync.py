"""State serialization and hydration helpers for networked matches."""

from __future__ import annotations

from typing import Any, Iterable

from core.card import Card
from core.game_state import GameState, Phase
from core.player import Player


def _player_key(game: GameState, player: Player) -> str:
    return "p1" if game.players[0] is player else "p2"


def _owner_for_card(game: GameState, card: Card) -> tuple[str, str] | None:
    for idx, player in enumerate(game.players):
        owner = "p1" if idx == 0 else "p2"
        if card in player.on_field:
            return owner, "field"
        if card in player.hand:
            return owner, "hand"
        if card in player.discard:
            return owner, "discard"
    return None


def serialize_card(card: Card) -> dict[str, Any]:
    statuses = getattr(card, "statuses", set()) or set()
    if isinstance(statuses, list):
        statuses = set(statuses)
    return {
        "id": int(id(card)),
        "title": card.title,
        "hp": int(card.hp),
        "max_hp": int(getattr(card, "max_hp", card.hp) or card.hp),
        "effect_type": str(getattr(card, "effect_type", "NONE") or "NONE"),
        "trigger": str(getattr(card, "ability_trigger", "") or ""),
        "ability_text": str(getattr(card, "ability_text", "") or ""),
        "ability_value": int(getattr(card, "ability_value", 0) or 0),
        "rarity": str(getattr(card, "rarity", "COMMON") or "COMMON"),
        "theme": str(getattr(card, "theme", "CONCEPTS") or "CONCEPTS"),
        "epoch": str(getattr(card, "epoch", "TIMELESS") or "TIMELESS"),
        "nemesis": getattr(card, "nemesis", None),
        "graveyard_eligible": bool(getattr(card, "graveyard_eligible", False)),
        "statuses": sorted(statuses),
        "silenced_turns": int(getattr(card, "silenced_turns", 0) or 0),
        "description": str(getattr(card, "description", "") or ""),
        "extract": str(getattr(card, "extract", "") or ""),
    }


def _serialize_target_ref(game: GameState, card: Card) -> dict[str, Any]:
    owner_zone = _owner_for_card(game, card)
    owner, zone = owner_zone if owner_zone is not None else ("p1", "field")
    return {
        "card_id": int(id(card)),
        "card_title": card.title,
        "owner": owner,
        "zone": zone,
    }


def serialize_targeting(game: GameState) -> dict[str, Any]:
    state = game.targeting_state
    if not bool(state.get("active")):
        return {"active": False}
    owner = state.get("owner")
    owner_key = _player_key(game, owner) if isinstance(owner, Player) and owner in game.players else None
    source = state.get("source_card")
    source_ref = _serialize_target_ref(game, source) if isinstance(source, Card) else None
    valid = [_serialize_target_ref(game, card) for card in list(state.get("valid_targets", []))]
    return {
        "active": True,
        "owner": owner_key,
        "effect_type": str(state.get("effect_type") or ""),
        "target_side": str(state.get("target_side") or ""),
        "prompt": str(state.get("prompt") or ""),
        "source": source_ref,
        "valid_targets": valid,
    }


def serialize_state(game: GameState) -> dict[str, Any]:
    p1, p2 = game.players
    return {
        "p1": {
            "name": p1.name,
            "field": [serialize_card(c) for c in p1.on_field],
            "hand": [serialize_card(c) for c in p1.hand],
            "deck": [serialize_card(c) for c in p1.deck],
            "deck_count": len(p1.deck),
            "discard": [serialize_card(c) for c in p1.discard],
            "gold": int(p1.gold),
        },
        "p2": {
            "name": p2.name,
            "field": [serialize_card(c) for c in p2.on_field],
            "hand": [serialize_card(c) for c in p2.hand],
            "deck": [serialize_card(c) for c in p2.deck],
            "deck_count": len(p2.deck),
            "discard": [serialize_card(c) for c in p2.discard],
            "gold": int(p2.gold),
        },
        "turn": int(game.turn_number),
        "active_player": _player_key(game, game.active_player),
        "phase": game.phase.value,
        "main_action_taken": bool(game.main_action_taken),
        "last_event": str(game.last_event or ""),
        "action_log": list(game.action_log),
        "targeting": serialize_targeting(game),
    }


def _deserialize_cards(cards: Iterable[dict[str, Any]]) -> list[Card]:
    result: list[Card] = []
    for payload in cards:
        statuses = payload.get("statuses", [])
        if isinstance(statuses, set):
            normalized = statuses
        elif isinstance(statuses, list):
            normalized = set(str(s) for s in statuses)
        else:
            normalized = set()
        card = Card(
            title=str(payload.get("title", "Unknown")),
            hp=int(payload.get("hp", 1) or 1),
            max_hp=int(payload.get("max_hp", payload.get("hp", 1)) or 1),
            theme=str(payload.get("theme", "CONCEPTS") or "CONCEPTS"),
            rarity=str(payload.get("rarity", "COMMON") or "COMMON"),
            epoch=str(payload.get("epoch", "TIMELESS") or "TIMELESS"),
            nemesis=payload.get("nemesis"),
            description=str(payload.get("description", "") or ""),
            extract=str(payload.get("extract", "") or ""),
            ability_text=str(payload.get("ability_text", "") or ""),
            ability_trigger=str(payload.get("trigger", "") or ""),
            effect_type=str(payload.get("effect_type", "NONE") or "NONE"),
            ability_value=int(payload.get("ability_value", 0) or 0),
            graveyard_eligible=bool(payload.get("graveyard_eligible", False)),
            statuses=normalized,
            silenced_turns=int(payload.get("silenced_turns", 0) or 0),
            image=None,
        )
        card.network_id = int(payload.get("id", 0) or 0)
        result.append(card)
    return result


def _find_card_ref(game: GameState, ref: dict[str, Any] | None) -> Card | None:
    if not ref:
        return None
    owner_key = str(ref.get("owner", "")).lower()
    zone = str(ref.get("zone", "field")).lower()
    card_id = int(ref.get("card_id", 0) or 0)
    card_title = str(ref.get("card_title", ""))
    if owner_key == "p1":
        player = game.players[0]
    elif owner_key == "p2":
        player = game.players[1]
    else:
        return None
    cards = (
        player.on_field
        if zone == "field"
        else player.hand
        if zone == "hand"
        else player.discard
    )
    for card in cards:
        if int(getattr(card, "network_id", 0) or 0) == card_id and card_id != 0:
            return card
    for card in cards:
        if card.title == card_title:
            return card
    return None


def _apply_targeting(game: GameState, payload: dict[str, Any] | None) -> None:
    if not isinstance(payload, dict) or not payload.get("active"):
        game.targeting_state = {
            "active": False,
            "source_card": None,
            "effect_type": None,
            "valid_targets": [],
            "target_side": None,
            "callback": None,
            "owner": None,
            "prompt": "",
        }
        return
    owner_key = str(payload.get("owner", "")).lower()
    owner = game.players[0] if owner_key == "p1" else game.players[1] if owner_key == "p2" else None
    source = _find_card_ref(game, payload.get("source"))
    valid_targets = [_find_card_ref(game, ref) for ref in list(payload.get("valid_targets", []))]
    game.targeting_state = {
        "active": True,
        "source_card": source,
        "effect_type": str(payload.get("effect_type", "") or ""),
        "valid_targets": [card for card in valid_targets if card is not None],
        "target_side": str(payload.get("target_side", "") or ""),
        "callback": None,
        "owner": owner,
        "prompt": str(payload.get("prompt", "") or ""),
    }


def apply_serialized_state(game: GameState, state: dict[str, Any]) -> None:
    p1_data = dict(state.get("p1", {}))
    p2_data = dict(state.get("p2", {}))
    p1, p2 = game.players
    p1.name = str(p1_data.get("name", "P1") or "P1")
    p2.name = str(p2_data.get("name", "P2") or "P2")
    p1.on_field = _deserialize_cards(list(p1_data.get("field", [])))
    p1.hand = _deserialize_cards(list(p1_data.get("hand", [])))
    p1.discard = _deserialize_cards(list(p1_data.get("discard", [])))
    if "deck" in p1_data:
        p1.deck = _deserialize_cards(list(p1_data.get("deck", [])))
    else:
        p1.deck = [None] * int(p1_data.get("deck_count", 0) or 0)
    p1.gold = int(p1_data.get("gold", 0) or 0)
    p2.on_field = _deserialize_cards(list(p2_data.get("field", [])))
    p2.hand = _deserialize_cards(list(p2_data.get("hand", [])))
    p2.discard = _deserialize_cards(list(p2_data.get("discard", [])))
    if "deck" in p2_data:
        p2.deck = _deserialize_cards(list(p2_data.get("deck", [])))
    else:
        p2.deck = [None] * int(p2_data.get("deck_count", 0) or 0)
    p2.gold = int(p2_data.get("gold", 0) or 0)

    game.turn_number = int(state.get("turn", 1) or 1)
    phase_value = str(state.get("phase", "MAIN") or "MAIN").upper()
    game.phase = Phase(phase_value) if phase_value in {p.value for p in Phase} else Phase.MAIN
    game.main_action_taken = bool(state.get("main_action_taken", False))
    game.last_event = str(state.get("last_event", "") or "")
    game.action_log = [str(line) for line in list(state.get("action_log", []))][-20:]
    active_player = str(state.get("active_player", "p1")).lower()
    game.active_idx = 0 if active_player == "p1" else 1
    _apply_targeting(game, state.get("targeting"))
