"""Runtime card effects for match engine."""

from __future__ import annotations

import random
from enum import Enum
from typing import TYPE_CHECKING, Optional

from data.settings_service import get_int

if TYPE_CHECKING:
    from core.card import Card
    from core.game_state import GameState
    from core.player import Player


class Effect(Enum):
    NONE = "NONE"
    HEAL_SELF_2 = "HEAL_SELF_2"
    DRAW_1 = "DRAW_1"
    DAMAGE_ENEMY_2 = "DAMAGE_ENEMY_2"
    BUFF_SELF_1 = "BUFF_SELF_1"


EFFECT_LABEL = {
    Effect.NONE: "",
    Effect.HEAL_SELF_2: "Heal 2",
    Effect.DRAW_1: "Draw 1",
    Effect.DAMAGE_ENEMY_2: "Zap 2",
    Effect.BUFF_SELF_1: "Vitality 2",
}

TARGETED_EFFECTS = {
    "DAMAGE",
    "DESTROY",
    "BANISH",
    "HEAL",
    "BLEEDING",
    "POISON",
    "VITALITY",
    "SHIELD",
    "IMMUNITY",
    "LOCK",
    "VEIL",
    "DUEL",
    "CLASH",
    "REVIVE",
}

def random_field_card(cards: list["Card"]) -> Optional["Card"]:
    if not cards:
        return None
    return random.choice(cards)


def _legacy_effect_to_runtime(effect: Effect) -> tuple[str, int]:
    if effect == Effect.DAMAGE_ENEMY_2:
        return "DAMAGE", 2
    if effect == Effect.HEAL_SELF_2:
        return "HEAL", 2
    if effect == Effect.DRAW_1:
        return "DRAW", 1
    if effect == Effect.BUFF_SELF_1:
        return "VITALITY", 2
    return "NONE", 0


def _normalize_effect_name(effect: str) -> str:
    normalized = str(effect or "NONE").strip().upper()
    if normalized == "BOOST":
        return "VITALITY"
    if normalized == "DRAIN":
        return "DAMAGE"
    return normalized


def _ensure_statuses(card: "Card") -> None:
    raw_statuses = getattr(card, "statuses", {})
    if raw_statuses is None:
        card.statuses = {}
    elif isinstance(raw_statuses, dict):
        normalized: dict[str, int | bool] = {}
        for name, value in raw_statuses.items():
            status = str(name).upper()
            if isinstance(value, bool):
                if value:
                    normalized[status] = True
            else:
                try:
                    qty = int(value)
                except Exception:
                    qty = 1
                if qty > 0:
                    normalized[status] = qty
        card.statuses = normalized
    elif isinstance(raw_statuses, (list, set, tuple)):
        card.statuses = {str(name).upper(): 1 for name in raw_statuses}
    else:
        card.statuses = {}

    if not hasattr(card, "silenced_turns"):
        card.silenced_turns = 0
    if not hasattr(card, "max_hp") or int(card.max_hp) <= 0:
        card.max_hp = max(1, int(card.hp))


def _status_count(card: "Card", status: str) -> int:
    _ensure_statuses(card)
    value = card.statuses.get(status.upper(), 0)
    if isinstance(value, bool):
        return 1 if value else 0
    try:
        return max(0, int(value))
    except Exception:
        return 0


def _status_enabled(card: "Card", status: str) -> bool:
    _ensure_statuses(card)
    value = card.statuses.get(status.upper(), 0)
    if isinstance(value, bool):
        return value
    try:
        return int(value) > 0
    except Exception:
        return False


def _set_status(card: "Card", status: str, value: int | bool) -> None:
    _ensure_statuses(card)
    name = status.upper()
    if isinstance(value, bool):
        if value:
            card.statuses[name] = True
        else:
            card.statuses.pop(name, None)
        return
    if int(value) > 0:
        card.statuses[name] = int(value)
    else:
        card.statuses.pop(name, None)


def _add_status_stack(card: "Card", status: str, amount: int = 1) -> int:
    _ensure_statuses(card)
    name = status.upper()
    current = _status_count(card, name)
    updated = max(0, current + max(0, int(amount)))
    if updated > 0:
        card.statuses[name] = updated
    else:
        card.statuses.pop(name, None)
    return updated


def _enemy_of(game: "GameState", owner: "Player") -> "Player":
    return game.players[1 - game.players.index(owner)]


def _debug(game: "GameState", message: str, *, include_state: bool = False) -> None:
    if hasattr(game, "debug"):
        game.debug(message, include_state=include_state)


def _target_prompt(effect: str, side: str) -> str:
    if effect in {"DAMAGE", "DESTROY", "BANISH", "DUEL", "CLASH", "BLEEDING", "POISON", "LOCK"}:
        return "Choose an enemy card."
    if effect in {"HEAL", "VITALITY", "SHIELD", "IMMUNITY", "VEIL"}:
        return "Choose a friendly card."
    if effect == "REVIVE":
        return "Choose a card to revive from discard."
    if side == "enemy":
        return "Select an enemy target."
    if side == "friendly":
        return "Select a friendly target."
    if side == "discard":
        return "Select a card from discard."
    return "Select a target."


def _can_be_targeted(card: "Card", *, by_ability: bool = True) -> bool:
    if _status_enabled(card, "IMMUNITY"):
        return False
    if by_ability and _status_enabled(card, "VEIL"):
        return False
    return True


def _filter_targetable(cards: list["Card"]) -> list["Card"]:
    return [c for c in cards if _can_be_targeted(c, by_ability=True)]


def _valid_targets(
    card: "Card",
    game: "GameState",
    owner: "Player",
    effect: str,
    value: int,
) -> tuple[list["Card"], str]:
    _ = card
    enemy = _enemy_of(game, owner)
    if effect in {"DAMAGE", "DESTROY", "BANISH", "BLEEDING", "POISON", "LOCK", "DUEL", "CLASH"}:
        return _filter_targetable(list(enemy.on_field)), "enemy"
    if effect in {"HEAL", "VITALITY", "SHIELD", "IMMUNITY", "VEIL"}:
        return _filter_targetable(list(owner.on_field)), "friendly"
    if effect == "REVIVE":
        return list(owner.discard), "discard"
    return [], "enemy"


def _consume_protection(target: "Card", amount: int) -> int:
    """Apply SHIELD/ARMOR mitigation and return remaining HP damage."""
    _ensure_statuses(target)
    if amount <= 0:
        return 0
    if _status_enabled(target, "SHIELD"):
        target.statuses.pop("SHIELD", None)
        return 0
    armor = _status_count(target, "ARMOR")
    if armor > 0:
        absorbed = min(armor, amount)
        amount -= absorbed
        _set_status(target, "ARMOR", armor - absorbed)
    return max(0, amount)


def _deal_damage(target: "Card", amount: int) -> int:
    remaining = _consume_protection(target, amount)
    if remaining <= 0:
        return 0
    target.hp -= remaining
    return remaining


def _kill_if_needed(
    game: "GameState",
    owner: "Player",
    target: "Card",
    killer_card: Optional["Card"],
    killer_owner: Optional["Player"],
) -> bool:
    if target.hp <= 0 and target in owner.on_field:
        game.kill_card(owner, target, killer_card=killer_card, killer_owner=killer_owner)
        return True
    return False


def apply_effect(
    card: "Card",
    game: "GameState",
    owner: "Player",
    target: Optional["Card"] = None,
) -> Optional[str]:
    """Apply card effect for owner and return human-readable match log line."""
    effect = _normalize_effect_name(str(getattr(card, "effect_type", "NONE") or "NONE"))
    value = int(getattr(card, "ability_value", 0) or 0)
    enemy = _enemy_of(game, owner)
    _debug(
        game,
        f"EFFECT begin card={card.title} owner={owner.name} effect={effect} value={value} "
        f"owner_field={len(owner.on_field)} enemy_field={len(enemy.on_field)}",
    )

    if effect == "NONE":
        legacy = getattr(card, "on_play", Effect.NONE)
        if legacy == Effect.NONE:
            legacy = getattr(card, "on_death", Effect.NONE)
        effect, legacy_value = _legacy_effect_to_runtime(legacy)
        if value <= 0:
            value = legacy_value
        _debug(game, f"EFFECT fallback to legacy mapping for {card.title}: effect={effect}, value={value}")

    if effect == "NONE":
        _debug(game, f"EFFECT skipped for {card.title}: NONE.")
        return None

    needs_target = effect in TARGETED_EFFECTS
    if needs_target and target is None:
        valid_targets, target_side = _valid_targets(card, game, owner, effect, value)
        if not valid_targets:
            _debug(game, f"EFFECT {effect} no valid targets for {card.title}.")
            return f"{card.title}: No valid targets."
        auto_target = game.active_player is not owner or card not in owner.on_field
        if auto_target:
            chosen = random.choice(valid_targets)
            _debug(game, f"EFFECT {effect} auto-target selected {chosen.title} for {owner.name}.")
            return apply_effect(card, game, owner, target=chosen)
        prompt = _target_prompt(effect, target_side)
        game.request_targeting(
            source_card=card,
            effect_type=effect,
            valid_targets=valid_targets,
            target_side=target_side,
            owner=owner,
            prompt=prompt,
            callback=lambda chosen: apply_effect(card, game, owner, target=chosen),
        )
        return None

    if effect == "DAMAGE":
        if target is None or target not in enemy.on_field:
            return None
        dealt = _deal_damage(target, max(0, value))
        _debug(game, f"EFFECT DAMAGE target={target.title} dealt={dealt} hp={target.hp}.")
        if _kill_if_needed(game, enemy, target, card, owner):
            return f"{card.title}: Deal {dealt} damage to {target.title}. {target.title} was destroyed."
        return f"{card.title}: Deal {dealt} damage to {target.title}."

    if effect == "HEAL":
        if target is None or target not in owner.on_field:
            return None
        before = target.hp
        target.hp = max(1, int(target.max_hp))
        _debug(game, f"EFFECT HEAL target={target.title} hp {before}->{target.hp}.")
        return f"{card.title}: Heal {target.title} to full HP."

    if effect == "BLEEDING":
        if target is None or target not in enemy.on_field:
            return None
        turns = max(1, value)
        now = _add_status_stack(target, "BLEEDING", turns)
        return f"{card.title}: Give {target.title} Bleeding ({now})."

    if effect == "VITALITY":
        if target is None or target not in owner.on_field:
            return None
        turns = max(1, value)
        now = _add_status_stack(target, "VITALITY", turns)
        return f"{card.title}: Give {target.title} Vitality ({now})."

    if effect == "POISON":
        if target is None or target not in enemy.on_field:
            return None
        stacks = _add_status_stack(target, "POISON", 1)
        if stacks >= 2:
            game.kill_card(enemy, target, killer_card=card, killer_owner=owner)
            return f"{card.title}: Poison {target.title}. {target.title} is destroyed."
        return f"{card.title}: Poison {target.title}."

    if effect == "SHIELD":
        if target is None or target not in owner.on_field:
            return None
        _set_status(target, "SHIELD", True)
        return f"{card.title}: Give SHIELD to {target.title}."

    if effect == "IMMUNITY":
        if target is None or target not in owner.on_field:
            return None
        _set_status(target, "IMMUNITY", True)
        return f"{card.title}: Give IMMUNITY to {target.title}."

    if effect == "LOCK":
        if target is None or target not in enemy.on_field:
            return None
        target.silenced_turns = 999
        _set_status(target, "LOCK", True)
        return f"{card.title}: Lock {target.title}."

    if effect == "VEIL":
        if target is None or target not in owner.on_field:
            return None
        _set_status(target, "VEIL", True)
        return f"{card.title}: Give VEIL to {target.title}."

    if effect == "DESTROY":
        if target is None or target not in enemy.on_field:
            return None
        game.kill_card(enemy, target, killer_card=card, killer_owner=owner)
        return f"{card.title}: Destroy {target.title}."

    if effect == "BANISH":
        if target is None or target not in enemy.on_field:
            return None
        enemy.on_field.remove(target)
        target.hp = 0
        target.graveyard_eligible = False
        _debug(game, f"EFFECT BANISH removed {target.title} from field without discard.")
        return f"{card.title}: Banish {target.title}."

    if effect == "DUEL":
        if target is None or target not in enemy.on_field:
            return None
        attacker = card
        defender = target
        while attacker.hp > 0 and defender.hp > 0:
            defender.hp -= attacker.hp
            if defender.hp <= 0:
                game.kill_card(enemy, defender, killer_card=card, killer_owner=owner)
                break
            attacker.hp -= defender.hp
            if attacker.hp <= 0:
                game.kill_card(owner, attacker, killer_card=defender, killer_owner=enemy)
                break
        return f"{card.title}: Duel {target.title}."

    if effect == "CLASH":
        if target is None or target not in enemy.on_field:
            return None
        dmg_to_target = max(0, card.hp)
        dmg_to_source = max(0, target.hp)
        dealt_to_target = _deal_damage(target, dmg_to_target)
        dealt_to_source = _deal_damage(card, dmg_to_source)
        if target.hp <= 0:
            game.kill_card(enemy, target, killer_card=card, killer_owner=owner)
        if card.hp <= 0 and card in owner.on_field:
            game.kill_card(owner, card, killer_card=target, killer_owner=enemy)
        return (
            f"{card.title}: Clash with {target.title} "
            f"({dealt_to_target}/{dealt_to_source})."
        )

    if effect == "DRAW":
        drew = 0
        for _ in range(max(0, value)):
            if not owner.deck:
                break
            if owner.draw_card() is not None:
                drew += 1
        if drew == 0:
            return None
        return f"{card.title}: Draw {drew} cards."

    if effect == "DISCARD":
        dropped = 0
        for _ in range(max(0, value)):
            if not enemy.hand:
                break
            idx = random.randrange(len(enemy.hand))
            discarded = enemy.hand.pop(idx)
            discarded.graveyard_eligible = True
            enemy.discard.append(discarded)
            dropped += 1
        if dropped == 0:
            return None
        return f"{card.title}: Enemy discards {dropped} cards."

    if effect == "REVIVE":
        if target is None or target not in owner.discard:
            return None
        if len(owner.on_field) >= get_int("gameplay.field_limit"):
            return None
        owner.discard.remove(target)
        revived = target
        _ensure_statuses(revived)
        revived.hp = max(1, revived.max_hp // 2)
        owner.on_field.append(revived)
        return f"{card.title}: {revived.title} revived to the field."

    if effect in {"MOVE", "SUMMON", "RANDOM"}:
        return f"{card.title}: {card.ability_text}".strip()

    _debug(game, f"EFFECT unknown effect_type={effect} for {card.title}.")
    return None
