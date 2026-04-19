"""Runtime card effects for match engine."""

from __future__ import annotations

import random
from enum import Enum
from typing import TYPE_CHECKING, Optional

from config import FIELD_LIMIT

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
    Effect.BUFF_SELF_1: "Empower +1 SC",
}

TARGETED_EFFECTS = {
    "DAMAGE",
    "EXECUTE",
    "BRIBE",
    "HEAL",
    "APPLY_SHIELD",
    "APPLY_VIGOR",
    "APPLY_IMMUNITY",
    "REVIVE",
    "APPLY_PLAGUE",
    "APPLY_DECAY",
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
        return "APPLY_FLOURISH", 0
    return "NONE", 0


def _ensure_statuses(card: "Card") -> None:
    if not hasattr(card, "statuses") or card.statuses is None:
        card.statuses = set()
    elif isinstance(card.statuses, list):
        card.statuses = set(card.statuses)
    elif not isinstance(card.statuses, set):
        card.statuses = set()
    if not hasattr(card, "silenced_turns"):
        card.silenced_turns = 0
    if not hasattr(card, "max_hp") or int(card.max_hp) <= 0:
        card.max_hp = max(1, int(card.hp))


def _add_status(
    card: "Card",
    status: str,
    game: Optional["GameState"] = None,
) -> bool:
    _ensure_statuses(card)
    if status in {"PLAGUE", "DECAY"} and "SHIELD" in card.statuses:
        card.statuses.remove("SHIELD")
        if game is not None:
            _plain_log(game, f"SHIELD blocked {status} on {card.title}")
            _debug(game, f"STATUS block target={card.title} blocked={status} via SHIELD.")
        return False
    card.statuses.add(status)
    return True


def _enemy_of(game: "GameState", owner: "Player") -> "Player":
    return game.players[1 - game.players.index(owner)]


def _debug(game: "GameState", message: str, *, include_state: bool = False) -> None:
    if hasattr(game, "debug"):
        game.debug(message, include_state=include_state)


def _plain_log(game: "GameState", message: str) -> None:
    if hasattr(game, "plain_log"):
        game.plain_log(message)
    else:
        print(f"[match] {message}", flush=True)


def _plague_targets_all_enemies(card: "Card") -> bool:
    text = str(getattr(card, "ability_text", "") or "").lower()
    return "all enemy" in text


def _target_prompt(effect: str, side: str) -> str:
    if effect == "DAMAGE":
        return "Choose an enemy card to damage."
    if effect == "EXECUTE":
        return "Choose an enemy card to execute."
    if effect == "BRIBE":
        return "Choose an enemy card to silence."
    if effect == "HEAL":
        return "Choose a friendly card to heal."
    if effect == "APPLY_SHIELD":
        return "Choose a friendly card to shield."
    if effect == "APPLY_VIGOR":
        return "Choose a friendly card for VIGOR."
    if effect == "APPLY_IMMUNITY":
        return "Choose a friendly card for IMMUNITY."
    if effect == "REVIVE":
        return "Choose a card to revive from discard."
    if effect == "APPLY_PLAGUE":
        return "Choose an enemy card for PLAGUE."
    if effect == "APPLY_DECAY":
        return "Choose an enemy card for DECAY."
    if side == "enemy":
        return "Select an enemy target."
    if side == "friendly":
        return "Select a friendly target."
    if side == "discard":
        return "Select a card from discard."
    return "Select a target."


def _valid_targets(
    card: "Card",
    game: "GameState",
    owner: "Player",
    effect: str,
    value: int,
) -> tuple[list["Card"], str]:
    enemy = _enemy_of(game, owner)
    if effect in {"DAMAGE", "EXECUTE", "BRIBE", "APPLY_PLAGUE", "APPLY_DECAY"}:
        targets = list(enemy.on_field)
        if effect == "EXECUTE":
            targets = [c for c in targets if c.hp <= value]
        return targets, "enemy"
    if effect in {"HEAL", "APPLY_SHIELD", "APPLY_VIGOR", "APPLY_IMMUNITY"}:
        return list(owner.on_field), "friendly"
    if effect == "REVIVE":
        return list(owner.discard), "discard"
    return [], "enemy"


def apply_effect(
    card: "Card",
    game: "GameState",
    owner: "Player",
    target: Optional["Card"] = None,
) -> Optional[str]:
    """Apply card effect for owner and return human-readable match log line."""
    effect = str(getattr(card, "effect_type", "NONE") or "NONE").upper()
    value = int(getattr(card, "ability_value", 0) or 0)
    enemy = _enemy_of(game, owner)
    _debug(
        game,
        f"EFFECT begin card={card.title} owner={owner.name} effect={effect} value={value} "
        f"owner_field={len(owner.on_field)} enemy_field={len(enemy.on_field)}",
    )

    # Backward compatibility for legacy starter cards.
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

    needs_target = effect in TARGETED_EFFECTS and not (effect == "APPLY_PLAGUE" and _plague_targets_all_enemies(card))
    if needs_target and target is None:
        valid_targets, target_side = _valid_targets(card, game, owner, effect, value)
        if not valid_targets:
            if effect == "EXECUTE":
                msg = f"EXECUTE skipped — no valid targets with HP <= {value}"
                _plain_log(game, msg)
                _debug(game, f"EFFECT EXECUTE no valid targets for {card.title} threshold={value}.")
                return msg
            if effect == "DAMAGE":
                msg = "DAMAGE skipped — no valid targets"
                _plain_log(game, msg)
                _debug(game, f"EFFECT DAMAGE no valid targets for {card.title}.")
                return msg
            _debug(game, f"EFFECT {effect} no valid targets for {card.title}.")
            return f"{card.title}: No valid targets."
        auto_target = owner.name == "P2" or game.active_player is not owner or card not in owner.on_field
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
            _debug(game, f"EFFECT DAMAGE no target for {card.title}.")
            return None
        before = target.hp
        target.hp -= value
        _debug(game, f"EFFECT DAMAGE target={target.title} hp {before}->{target.hp}.")
        if target.hp <= 0:
            game.kill_card(enemy, target)
            return f"{card.title}: Deal {value} damage to {target.title}. {target.title} was destroyed."
        return f"{card.title}: Deal {value} damage to {target.title}."

    if effect == "HEAL":
        if target is None or target not in owner.on_field:
            _debug(game, f"EFFECT HEAL no target for {card.title}.")
            return None
        _ensure_statuses(target)
        before = target.hp
        target.hp = min(target.hp + value, target.max_hp)
        _debug(game, f"EFFECT HEAL target={target.title} hp {before}->{target.hp}.")
        return f"{card.title}: Restore {value} HP to {target.title}."

    if effect == "APPLY_PLAGUE":
        if target is not None:
            if target not in enemy.on_field:
                _debug(game, f"EFFECT APPLY_PLAGUE invalid target for {card.title}.")
                return None
            _add_status(target, "PLAGUE", game)
            _debug(game, f"EFFECT APPLY_PLAGUE target={target.title}.")
            return f"{card.title}: Apply PLAGUE to {target.title}."
        if not enemy.on_field:
            _debug(game, f"EFFECT APPLY_PLAGUE no enemy cards for {card.title}.")
            return None
        for c in enemy.on_field:
            _add_status(c, "PLAGUE", game)
        _debug(game, f"EFFECT APPLY_PLAGUE applied to {len(enemy.on_field)} cards.")
        return f"{card.title}: Apply PLAGUE to all enemy cards."

    if effect == "APPLY_VIGOR":
        if target is None or target not in owner.on_field:
            _debug(game, f"EFFECT APPLY_VIGOR no friendly cards for {card.title}.")
            return None
        _add_status(target, "VIGOR", game)
        _debug(game, f"EFFECT APPLY_VIGOR target={target.title}.")
        return f"{card.title}: Apply VIGOR to {target.title}."

    if effect == "APPLY_DECAY":
        if target is None or target not in enemy.on_field:
            _debug(game, f"EFFECT APPLY_DECAY no target for {card.title}.")
            return None
        _add_status(target, "DECAY", game)
        _debug(game, f"EFFECT APPLY_DECAY target={target.title}.")
        return f"{card.title}: Apply DECAY to {target.title}."

    if effect == "APPLY_FLOURISH":
        if not owner.on_field:
            _debug(game, f"EFFECT APPLY_FLOURISH no friendly cards for {card.title}.")
            return None
        for c in owner.on_field:
            _add_status(c, "FLOURISH", game)
        _debug(game, f"EFFECT APPLY_FLOURISH applied to {len(owner.on_field)} cards.")
        return f"{card.title}: Apply FLOURISH to all friendly cards."

    if effect == "APPLY_SHIELD":
        if target is None or target not in owner.on_field:
            _debug(game, f"EFFECT APPLY_SHIELD invalid target for {card.title}.")
            return None
        _add_status(target, "SHIELD", game)
        _debug(game, f"EFFECT APPLY_SHIELD target={target.title}.")
        return f"{card.title}: Apply SHIELD to {target.title}."

    if effect == "APPLY_IMMUNITY":
        if target is None or target not in owner.on_field:
            _debug(game, f"EFFECT APPLY_IMMUNITY invalid target for {card.title}.")
            return None
        _add_status(target, "IMMUNITY", game)
        _debug(game, f"EFFECT APPLY_IMMUNITY target={target.title}.")
        return f"{card.title}: Apply IMMUNITY to {target.title}."

    if effect == "DRAW":
        drew = 0
        for _ in range(max(0, value)):
            if not owner.deck:
                _debug(game, f"EFFECT DRAW deck empty after {drew} cards for {owner.name}.")
                break
            owner.hand.append(owner.deck.pop(0))
            drew += 1
        if drew == 0:
            _debug(game, f"EFFECT DRAW drew 0 cards for {card.title}.")
            return None
        _debug(game, f"EFFECT DRAW drew={drew} for {owner.name}.")
        return f"{card.title}: Draw {drew} cards."

    if effect == "DISCARD":
        dropped = 0
        for _ in range(max(0, value)):
            if not enemy.hand:
                _debug(game, f"EFFECT DISCARD enemy hand empty after {dropped} discards.")
                break
            idx = random.randrange(len(enemy.hand))
            enemy.discard.append(enemy.hand.pop(idx))
            dropped += 1
        if dropped == 0:
            _debug(game, f"EFFECT DISCARD dropped 0 cards for {card.title}.")
            return None
        _debug(game, f"EFFECT DISCARD dropped={dropped} from {enemy.name}.")
        return f"{card.title}: Enemy discards {dropped} cards."

    if effect == "GOLD":
        owner.gold += max(0, value)
        _debug(game, f"EFFECT GOLD owner={owner.name} +{max(0, value)} => {owner.gold}.")
        return f"{card.title}: Gain {max(0, value)} gold."

    if effect == "EXECUTE":
        if target is None or target not in enemy.on_field:
            _debug(game, f"EFFECT EXECUTE invalid target for {card.title}.")
            return None
        if target.hp > value:
            _debug(game, f"EFFECT EXECUTE target {target.title} HP={target.hp} > {value}.")
            return None
        target_hp = target.hp
        _debug(game, f"EFFECT EXECUTE target={target.title} hp={target_hp} threshold={value}.")
        game.kill_card(enemy, target)
        return f"{card.title}: {target.title} executed ({target_hp} HP <= {value})."

    if effect == "REVIVE":
        if target is None or target not in owner.discard:
            _debug(game, f"EFFECT REVIVE invalid target for {card.title}.")
            return None
        if len(owner.on_field) >= FIELD_LIMIT:
            _debug(
                game,
                f"EFFECT REVIVE blocked discard={len(owner.discard)} field={len(owner.on_field)}/{FIELD_LIMIT}.",
            )
            return None
        owner.discard.remove(target)
        revived = target
        _ensure_statuses(revived)
        revived.hp = max(1, revived.max_hp // 2)
        owner.on_field.append(revived)
        _debug(game, f"EFFECT REVIVE revived={revived.title} hp={revived.hp}/{revived.max_hp}.")
        return f"{card.title}: {revived.title} revived to the field."

    if effect == "BRIBE":
        if target is None or target not in enemy.on_field:
            _debug(game, f"EFFECT BRIBE no target for {card.title}.")
            return None
        _ensure_statuses(target)
        target.silenced_turns = 1
        _debug(game, f"EFFECT BRIBE target={target.title} silenced_turns=1.")
        return f"{card.title}: {target.title} is silenced for 1 turn."

    if effect in {"MOVE", "SUMMON", "RANDOM"}:
        _debug(game, f"EFFECT passthrough {effect} text={card.ability_text!r}.")
        return f"{card.title}: {card.ability_text}".strip()

    _debug(game, f"EFFECT unknown effect_type={effect} for {card.title}.")
    return None
