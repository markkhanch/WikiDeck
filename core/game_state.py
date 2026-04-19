"""GameState — top-level match controller.

Stage 3 MVP:
 - Two players, hotseat on the same keyboard
 - Turns are DRAW → MAIN → (End Turn click) → swap player
 - MAIN is mandatory: must PLAY or DISCARD before End Turn activates
   (relaxed only if the active player's hand is empty)
 - Match ends when BOTH players have empty hand AND empty deck (GDD §5.1)
 - No combos, no triggers, no HP/damage yet — cards just stack on the field
"""
from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Callable, List

from core.card import Card
from core.combos import multiplier
from core.effects import apply_effect
from core.player import Player
from core.triggers import apply_status_ticks, fire_triggers


class Phase(Enum):
    DRAW = "DRAW"
    MAIN = "MAIN"
    END = "END"
    GAME_OVER = "GAME_OVER"


@dataclass
class GameState:
    players: List[Player] = field(default_factory=list)
    active_idx: int = 0
    turn_number: int = 1
    phase: Phase = Phase.DRAW
    main_action_taken: bool = False  # has the active player played or discarded this turn?
    last_event: str = ""             # short log line for the HUD
    action_log: List[str] = field(default_factory=list)
    verbose_terminal_logs: bool = True
    _debug_seq: int = 0
    _match_started_at: float = field(default_factory=time.time)
    pending_effects: List[tuple[Card, Player]] = field(default_factory=list)
    targeting_state: dict[str, Any] = field(
        default_factory=lambda: {
            "active": False,
            "source_card": None,
            "effect_type": None,
            "valid_targets": [],
            "target_side": None,
            "callback": None,
            "owner": None,
            "prompt": "",
        }
    )

    # ---- convenience ----
    @property
    def active_player(self) -> Player:
        return self.players[self.active_idx]

    @property
    def opponent(self) -> Player:
        return self.players[1 - self.active_idx]

    # ---- turn flow ----
    def start_match(self) -> None:
        """Call once after players and decks are set up. Runs first DRAW phase."""
        self._match_started_at = time.time()
        self._debug_seq = 0
        self.pending_effects.clear()
        self.targeting_state = {
            "active": False,
            "source_card": None,
            "effect_type": None,
            "valid_targets": [],
            "target_side": None,
            "callback": None,
            "owner": None,
            "prompt": "",
        }
        self.debug("Match created.", include_state=True)
        self.phase = Phase.DRAW
        self.start_turn()

    def _format_card_debug(self, card: Card) -> str:
        raw_statuses = getattr(card, "statuses", set()) or set()
        if isinstance(raw_statuses, list):
            statuses = ",".join(sorted(set(raw_statuses)))
        else:
            statuses = ",".join(sorted(raw_statuses))
        silence = int(getattr(card, "silenced_turns", 0) or 0)
        effect = str(getattr(card, "effect_type", "NONE") or "NONE")
        trigger = str(getattr(card, "ability_trigger", "NO ABILITY") or "NO ABILITY")
        return (
            f"{card.title}(HP={card.hp}/{max(1, int(getattr(card, 'max_hp', card.hp)))},"
            f"SC={card.base_score},eff={effect},trg={trigger},st=[{statuses}],sil={silence})"
        )

    def _format_player_snapshot(self, player: Player) -> str:
        hand = ", ".join(c.title for c in player.hand) or "-"
        deck = ", ".join(c.title for c in player.deck[:8]) + (" ..." if len(player.deck) > 8 else "")
        deck = deck or "-"
        field = ", ".join(self._format_card_debug(c) for c in player.on_field) or "-"
        discard = ", ".join(c.title for c in player.discard[-5:]) or "-"
        return (
            f"{player.name}: H[{len(player.hand)}]={hand} | "
            f"D[{len(player.deck)}]={deck} | "
            f"F[{len(player.on_field)}]={field} | "
            f"X[{len(player.discard)}]={discard} | "
            f"gold={player.gold}"
        )

    def _state_snapshot(self) -> str:
        active = self.active_player.name if self.players else "?"
        p1 = self._format_player_snapshot(self.players[0]) if len(self.players) > 0 else "p1: n/a"
        p2 = self._format_player_snapshot(self.players[1]) if len(self.players) > 1 else "p2: n/a"
        return (
            f"turn={self.turn_number} phase={self.phase.value} active={active} main_action={self.main_action_taken}\n"
            f"    {p1}\n"
            f"    {p2}"
        )

    def debug(self, message: str, *, include_state: bool = False) -> None:
        if not self.verbose_terminal_logs:
            return
        self._debug_seq += 1
        elapsed = time.time() - self._match_started_at
        print(f"[match][{self._debug_seq:04d}][+{elapsed:07.2f}s] {message}", flush=True)
        if include_state:
            for line in self._state_snapshot().splitlines():
                print(f"[match][state] {line}", flush=True)

    def plain_log(self, message: str) -> None:
        print(f"[match] {message}", flush=True)

    def is_targeting_active(self) -> bool:
        return bool(self.targeting_state.get("active"))

    def request_targeting(
        self,
        *,
        source_card: Card,
        effect_type: str,
        valid_targets: list[Card],
        target_side: str,
        owner: Player,
        prompt: str,
        callback: Callable[[Card], str | None] | None,
    ) -> None:
        self.targeting_state = {
            "active": True,
            "source_card": source_card,
            "effect_type": effect_type,
            "valid_targets": list(valid_targets),
            "target_side": target_side,
            "callback": callback,
            "owner": owner,
            "prompt": prompt,
        }
        self.debug(
            f"TARGETING requested: source={source_card.title} effect={effect_type} side={target_side} "
            f"targets={len(valid_targets)}",
            include_state=True,
        )
        self.log_event(prompt)

    def _clear_targeting_state(self) -> None:
        self.targeting_state = {
            "active": False,
            "source_card": None,
            "effect_type": None,
            "valid_targets": [],
            "target_side": None,
            "callback": None,
            "owner": None,
            "prompt": "",
        }

    def resolve_targeting(self, target: Card) -> bool:
        if not self.is_targeting_active():
            self.debug("TARGETING resolve ignored: no active targeting state.")
            return False
        valid = list(self.targeting_state.get("valid_targets", []))
        valid_ids = {id(card) for card in valid}
        if id(target) not in valid_ids:
            self.debug(
                f"TARGETING resolve ignored: invalid target {target.title} "
                f"(id={id(target)} not in valid_ids)."
            )
            return False
        target = next(card for card in valid if id(card) == id(target))
        callback = self.targeting_state.get("callback")
        source = self.targeting_state.get("source_card")
        self.debug(
            f"TARGETING resolved: source={getattr(source, 'title', '?')} target={target.title}",
            include_state=True,
        )
        self._clear_targeting_state()
        result = callback(target) if callable(callback) else None
        if result:
            self.log_event(result)
        self.flush_pending_effects()
        return True

    def cancel_targeting(self, reason: str = "Target selection cancelled.") -> None:
        if not self.is_targeting_active():
            return
        source = self.targeting_state.get("source_card")
        self.debug(f"TARGETING cancelled for source={getattr(source, 'title', '?')}.", include_state=True)
        self._clear_targeting_state()
        self.log_event(reason)
        self.flush_pending_effects()

    def queue_pending_effect(self, card: Card, owner: Player) -> None:
        for queued_card, queued_owner in self.pending_effects:
            if queued_card is card and queued_owner is owner:
                return
        self.pending_effects.append((card, owner))
        self.debug(f"Queued pending effect for {card.title} ({owner.name}).")

    def flush_pending_effects(self) -> None:
        while self.pending_effects and not self.is_targeting_active():
            card, owner = self.pending_effects.pop(0)
            self.debug(f"Dequeued pending effect for {card.title} ({owner.name}).")
            msg = apply_effect(card, self, owner)
            if msg:
                self.log_event(msg)

    def log_event(self, message: str) -> None:
        text = (message or "").strip()
        if not text:
            return
        self.last_event = text
        self.action_log.append(text)
        if len(self.action_log) > 5:
            self.action_log = self.action_log[-5:]
        self.debug(f"EVENT: {text}", include_state=True)

    def start_turn(self) -> None:
        """DRAW phase: auto-draw one card, then enter MAIN."""
        self.main_action_taken = False
        self.phase = Phase.DRAW
        drawn = self.active_player.draw_card()
        if drawn is None:
            self.debug(f"{self.active_player.name} DRAW: no cards left in deck.", include_state=True)
        else:
            self.debug(f"{self.active_player.name} DRAW: {drawn.title}.", include_state=True)
        self.debug(f"Firing START OF TURN for {self.active_player.name}.")
        fire_triggers("START OF TURN", self, self.active_player)
        self.phase = Phase.MAIN
        self.debug(f"{self.active_player.name} enters MAIN phase.", include_state=True)

    def try_play(self, card: Card) -> bool:
        """Attempt PLAY during MAIN. Returns True on success."""
        if self.phase != Phase.MAIN or self.main_action_taken:
            self.debug(
                f"PLAY blocked for {card.title}: phase={self.phase.value}, main_action_taken={self.main_action_taken}."
            )
            return False
        self.debug(f"PLAY attempt by {self.active_player.name}: {card.title}")
        if self.active_player.play_card(card):
            self.main_action_taken = True
            self.log_event(f"{self.active_player.name} plays {card.title}")
            self.debug(f"Firing ON PLAY triggers for {self.active_player.name}.", include_state=True)
            fire_triggers("ON PLAY", self, self.active_player, source_card=card)
            return True
        self.debug(f"PLAY failed for {card.title}: card not in hand or field limit reached.", include_state=True)
        return False

    def try_discard(self, card: Card) -> bool:
        """Attempt DISCARD during MAIN. Returns True on success."""
        if self.phase != Phase.MAIN or self.main_action_taken:
            self.debug(
                f"DISCARD blocked for {card.title}: phase={self.phase.value}, main_action_taken={self.main_action_taken}."
            )
            return False
        self.debug(f"DISCARD attempt by {self.active_player.name}: {card.title}")
        if self.active_player.discard_from_hand(card):
            self.main_action_taken = True
            self.log_event(f"{self.active_player.name} discards {card.title}")
            return True
        self.debug(f"DISCARD failed for {card.title}: not in hand.", include_state=True)
        return False

    def try_attack(self, attacker: Card, target: Card) -> bool:
        """Attack an enemy field card. Damage = attacker.base_score.

        MVP rule (not in GDD): active player's on-field card can attack once per turn,
        dealing damage equal to its base_score. This will be replaced by the real
        trigger-driven combat model once abilities are implemented.
        """
        if self.phase != Phase.MAIN or self.main_action_taken:
            self.debug(
                f"ATTACK blocked {attacker.title}->{target.title}: phase={self.phase.value}, main_action_taken={self.main_action_taken}."
            )
            return False
        if attacker not in self.active_player.on_field:
            self.debug(f"ATTACK blocked: attacker {attacker.title} not on active field.")
            return False
        if target not in self.opponent.on_field:
            self.debug(f"ATTACK blocked: target {target.title} not on opponent field.")
            return False

        before_hp = target.hp
        target.hp -= attacker.base_score
        self.debug(
            f"ATTACK resolved: {attacker.title} -> {target.title}, damage={attacker.base_score}, hp {before_hp}->{target.hp}."
        )
        self.log_event(f"{attacker.title} hits {target.title} for {attacker.base_score}")
        if target.hp <= 0:
            self.kill_card(self.opponent, target)
            self.log_event(f"{attacker.title} destroys {target.title}")

        self.main_action_taken = True
        return True

    def kill_card(self, owner: Player, dead_card: Card) -> None:
        if dead_card not in owner.on_field and dead_card in owner.discard:
            self.debug(f"KILL skipped for {dead_card.title}: already in discard.")
            return
        self.debug(f"KILL start for {dead_card.title} (owner={owner.name}).", include_state=True)
        dead_card.hp = 0
        if dead_card in owner.on_field:
            owner.on_field.remove(dead_card)
        if dead_card not in owner.discard:
            owner.discard.append(dead_card)
        enemy = self.players[1 - self.players.index(owner)]
        trigger = (dead_card.ability_trigger or "").strip().upper()
        if trigger in {"ON DEATH", "ON DEATH:SELF"}:
            self.debug(f"Applying ON DEATH:self for {dead_card.title}.")
            msg = apply_effect(dead_card, self, owner)
            if msg:
                self.log_event(msg)
        self.debug(f"Firing ON DEATH:ALLY for {owner.name}.")
        fire_triggers("ON DEATH:ALLY", self, owner, source_card=dead_card)
        self.debug(f"Firing ON DEATH:ENEMY for {enemy.name}.")
        fire_triggers("ON DEATH:ENEMY", self, enemy, source_card=dead_card)
        self.debug(f"KILL end for {dead_card.title}.", include_state=True)

    def handle_card_death(
        self,
        owner: Player,
        dead_card: Card,
        *,
        allow_chain_death: bool,
    ) -> str:
        _ = allow_chain_death
        self.kill_card(owner, dead_card)
        return self.last_event

    def can_end_turn(self) -> bool:
        if self.phase == Phase.GAME_OVER:
            return False
        if self.is_targeting_active():
            return False
        # Must have played or discarded, unless the hand is empty
        if self.main_action_taken:
            return True
        return len(self.active_player.hand) == 0

    def end_turn(self) -> None:
        if not self.can_end_turn():
            self.debug("END TURN blocked by can_end_turn() check.")
            return
        ending_owner = self.active_player
        ending_enemy = self.opponent
        self.debug(f"END TURN start by {ending_owner.name}.", include_state=True)
        self.phase = Phase.END
        self.debug(f"Firing END OF TURN for {ending_owner.name}.")
        fire_triggers("END OF TURN", self, ending_owner)
        self.debug(f"Firing END OF TURN for {ending_enemy.name}.")
        fire_triggers("END OF TURN", self, ending_enemy)
        self.debug(f"Applying status ticks for {ending_owner.name}.")
        apply_status_ticks(self, ending_owner)
        self.debug(f"Applying status ticks for {ending_enemy.name}.")
        apply_status_ticks(self, ending_enemy)
        self.active_idx = 1 - self.active_idx
        self.turn_number += 1
        self.debug("END TURN swap complete.", include_state=True)
        if self.is_match_over():
            self.phase = Phase.GAME_OVER
            self.debug("GAME OVER reached.", include_state=True)
            self._log_game_over_summary()
            return
        self.start_turn()

    # ---- match end ----
    def is_match_over(self) -> bool:
        return all(len(p.hand) == 0 and len(p.deck) == 0 for p in self.players)

    def base_sum(self, player: Player) -> int:
        """Raw Σ(base_score) over living field cards — no multiplier."""
        return sum(c.base_score for c in player.on_field)

    def multiplier_for(self, player: Player) -> float:
        return multiplier(player.on_field)

    def score_for(self, player: Player) -> int:
        """Final score = floor(base_sum × multiplier) (GDD §5.2)."""
        return int(self.base_sum(player) * self.multiplier_for(player))

    def _log_game_over_summary(self) -> None:
        p1, p2 = self.players

        def _field_line(player: Player) -> tuple[str, int, float, int]:
            if player.on_field:
                cards = ", ".join(
                    f"{c.title} HP={c.hp} SC={c.base_score}"
                    for c in player.on_field
                )
            else:
                cards = "(empty)"
            total = self.base_sum(player)
            mult = self.multiplier_for(player)
            score = self.score_for(player)
            return cards, total, mult, score

        p1_cards, p1_total, p1_mult, p1_score = _field_line(p1)
        p2_cards, p2_total, p2_mult, p2_score = _field_line(p2)

        self.plain_log("GAME OVER")
        self.plain_log(
            f"{p1.name} field: {p1_cards} -> total={p1_total} × {p1_mult:.1f} = {p1_score}"
        )
        self.plain_log(
            f"{p2.name} field: {p2_cards} -> total={p2_total} × {p2_mult:.1f} = {p2_score}"
        )
        self.plain_log(f"Multipliers: {p1.name}={p1_mult:.1f}, {p2.name}={p2_mult:.1f}")
        if p1_score > p2_score:
            self.plain_log(f"WINNER: {p1.name} ({p1_score} > {p2_score})")
        elif p2_score > p1_score:
            self.plain_log(f"WINNER: {p2.name} ({p2_score} > {p1_score})")
        else:
            self.plain_log(f"WINNER: DRAW ({p1_score} = {p2_score})")
