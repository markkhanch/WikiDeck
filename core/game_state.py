"""GameState — top-level match controller.

Stage 3 MVP:
 - Two players, hotseat on the same keyboard
 - Turns are DRAW → MAIN → (End Turn click) → swap player
 - MAIN is mandatory: must PLAY or DISCARD before End Turn activates
   (relaxed only if the active player's hand is empty)
 - Match ends when BOTH players have empty hand AND empty deck (GDD §5.1)
 - No score multipliers — winner is determined by total field HP
"""
from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Callable, List

from core.card import Card
from core.effects import _consume_protection, apply_effect
from core.player import Player
from core.triggers import apply_status_ticks, fire_triggers, normalize_trigger_name

ACTION_LOG_LIMIT = 20


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
        raw_statuses = getattr(card, "statuses", {}) or {}
        if isinstance(raw_statuses, dict):
            labels: list[str] = []
            for name in sorted(raw_statuses):
                value = raw_statuses[name]
                if isinstance(value, bool):
                    if value:
                        labels.append(name)
                    continue
                try:
                    qty = int(value)
                except Exception:
                    qty = 1
                if qty > 1:
                    labels.append(f"{name}:{qty}")
                elif qty == 1:
                    labels.append(name)
            statuses = ",".join(labels)
        elif isinstance(raw_statuses, list):
            statuses = ",".join(sorted(set(str(v) for v in raw_statuses)))
        else:
            statuses = ",".join(sorted(str(v) for v in raw_statuses))
        silence = int(getattr(card, "silenced_turns", 0) or 0)
        effect = str(getattr(card, "effect_type", "NONE") or "NONE")
        trigger = str(getattr(card, "ability_trigger", "NO ABILITY") or "NO ABILITY")
        return (
            f"{card.title}(HP={card.hp}/{max(1, int(getattr(card, 'max_hp', card.hp)))},"
            f"eff={effect},trg={trigger},st=[{statuses}],sil={silence})"
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
        if len(self.action_log) > ACTION_LOG_LIMIT:
            self.action_log = self.action_log[-ACTION_LOG_LIMIT:]
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
            trigger = normalize_trigger_name(getattr(card, "ability_trigger", ""))
            if trigger == "TIMER":
                statuses = getattr(card, "statuses", {})
                if not isinstance(statuses, dict):
                    statuses = {}
                    card.statuses = statuses
                statuses["TIMER"] = max(0, int(getattr(card, "trigger_value", 0) or 0))
            self.debug(f"Firing DEPLOY triggers for {self.active_player.name}.", include_state=True)
            fire_triggers("DEPLOY", self, self.active_player, source_card=card)
            self._check_adrenaline_triggers(self.active_player)
            self._check_adrenaline_triggers(self.opponent)
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
            self._check_adrenaline_triggers(self.active_player)
            self._check_adrenaline_triggers(self.opponent)
            return True
        self.debug(f"DISCARD failed for {card.title}: not in hand.", include_state=True)
        return False

    def try_attack(self, attacker: Card, target: Card) -> bool:
        """Attack an enemy field card with fixed damage.

        MVP rule (not in GDD): active player's on-field card can attack once per turn,
        dealing fixed damage. This will be replaced by the real
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

        raw_damage = 1
        dealt = _consume_protection(target, raw_damage)
        before_hp = target.hp
        target.hp -= dealt
        self.debug(
            f"ATTACK resolved: {attacker.title} -> {target.title}, damage={raw_damage}, dealt={dealt}, hp {before_hp}->{target.hp}."
        )
        self.log_event(f"{attacker.title} hits {target.title} for {dealt}")
        if target.hp <= 0:
            self.kill_card(self.opponent, target, killer_card=attacker, killer_owner=self.active_player)
            self.log_event(f"{attacker.title} destroys {target.title}")

        self.main_action_taken = True
        self._check_adrenaline_triggers(self.active_player)
        self._check_adrenaline_triggers(self.opponent)
        return True

    def try_order(self, card: Card) -> bool:
        """Activate ORDER / ORDER_ZEAL ability once per turn during MAIN."""
        if self.phase != Phase.MAIN or self.main_action_taken:
            self.debug(
                f"ORDER blocked for {card.title}: phase={self.phase.value}, main_action_taken={self.main_action_taken}."
            )
            return False
        if self.is_targeting_active():
            self.debug(f"ORDER blocked for {card.title}: targeting is active.")
            return False
        if card not in self.active_player.on_field:
            self.debug(f"ORDER blocked for {card.title}: card not on active field.")
            return False
        trigger = normalize_trigger_name(getattr(card, "ability_trigger", ""))
        if trigger not in {"ORDER", "ORDER_ZEAL"}:
            self.debug(f"ORDER blocked for {card.title}: trigger={trigger}.")
            return False
        if int(getattr(card, "silenced_turns", 0) or 0) > 0:
            self.debug(f"ORDER blocked for {card.title}: silenced_turns={card.silenced_turns}.")
            return False
        used_turn = int(getattr(card, "order_used_turn", -1) or -1)
        if used_turn == self.turn_number:
            self.debug(f"ORDER blocked for {card.title}: already used this turn.")
            return False

        setattr(card, "order_used_turn", self.turn_number)
        self.main_action_taken = True
        self.debug(f"ORDER attempt by {self.active_player.name}: {card.title}")
        msg = apply_effect(card, self, self.active_player)
        if msg:
            self.log_event(msg)
        else:
            self.debug(f"ORDER no-op for {card.title}.")
        self._check_adrenaline_triggers(self.active_player)
        self._check_adrenaline_triggers(self.opponent)
        return True

    def _check_adrenaline_triggers(self, owner: Player) -> None:
        for card in list(owner.on_field):
            if card not in owner.on_field:
                continue
            if normalize_trigger_name(getattr(card, "ability_trigger", "")) != "ADRENALINE":
                continue
            threshold = int(getattr(card, "trigger_value", 0) or 0)
            if len(owner.hand) <= threshold:
                msg = apply_effect(card, self, owner)
                if msg:
                    self.log_event(msg)

    def kill_card(
        self,
        owner: Player,
        dead_card: Card,
        *,
        killer_card: Card | None = None,
        killer_owner: Player | None = None,
    ) -> None:
        if dead_card not in owner.on_field and dead_card in owner.discard:
            self.debug(f"KILL skipped for {dead_card.title}: already in discard.")
            return
        self.debug(f"KILL start for {dead_card.title} (owner={owner.name}).", include_state=True)
        dead_card.hp = 0
        if dead_card in owner.on_field:
            owner.on_field.remove(dead_card)
        dead_card.graveyard_eligible = True
        dead_statuses = getattr(dead_card, "statuses", {})
        doomed = False
        if isinstance(dead_statuses, dict):
            doomed = bool(dead_statuses.get("DOOMED"))
        if not doomed and dead_card not in owner.discard:
            owner.discard.append(dead_card)
        enemy = self.players[1 - self.players.index(owner)]
        trigger = normalize_trigger_name(getattr(dead_card, "ability_trigger", ""))
        if trigger == "DEATHWISH":
            self.debug(f"Applying DEATHWISH for {dead_card.title}.")
            msg = apply_effect(dead_card, self, owner)
            if msg:
                self.log_event(msg)
        if killer_card is not None and killer_owner is not None:
            killer_owner.kills = int(getattr(killer_owner, "kills", 0) or 0) + 1
            if normalize_trigger_name(getattr(killer_card, "ability_trigger", "")) == "DEATHBLOW":
                deathblow_msg = apply_effect(killer_card, self, killer_owner)
                if deathblow_msg:
                    self.log_event(deathblow_msg)
        self.debug(f"Firing ON DEATH:ALLY for {owner.name}.")
        fire_triggers("ON DEATH:ALLY", self, owner, source_card=dead_card)
        self.debug(f"Firing ON DEATH:ENEMY for {enemy.name}.")
        fire_triggers("ON DEATH:ENEMY", self, enemy, source_card=dead_card)

        for blood_owner in self.players:
            kills = int(getattr(blood_owner, "kills", 0) or 0)
            for card in list(blood_owner.on_field):
                if card not in blood_owner.on_field:
                    continue
                if normalize_trigger_name(getattr(card, "ability_trigger", "")) != "BLOODTHIRST":
                    continue
                threshold = int(getattr(card, "trigger_value", 0) or 0)
                if kills >= threshold:
                    blood_msg = apply_effect(card, self, blood_owner)
                    if blood_msg:
                        self.log_event(blood_msg)

        self._check_adrenaline_triggers(owner)
        self._check_adrenaline_triggers(enemy)
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
        """Raw Σ(HP) over living field cards."""
        return sum(max(0, int(c.hp)) for c in player.on_field)

    def graveyard_eligible_count(self, player: Player) -> int:
        return sum(1 for card in player.discard if bool(getattr(card, "graveyard_eligible", False)))

    def score_for(self, player: Player) -> int:
        """Final score from field HP total."""
        return self.base_sum(player)

    def _log_game_over_summary(self) -> None:
        p1, p2 = self.players

        def _field_line(player: Player) -> tuple[str, int]:
            if player.on_field:
                cards = ", ".join(
                    f"{c.title} HP={c.hp}"
                    for c in player.on_field
                )
            else:
                cards = "(empty)"
            score = self.score_for(player)
            return cards, score

        p1_cards, p1_score = _field_line(p1)
        p2_cards, p2_score = _field_line(p2)

        self.plain_log("GAME OVER")
        self.plain_log(
            f"{p1.name} field: {p1_cards} -> score={p1_score}"
        )
        self.plain_log(
            f"{p2.name} field: {p2_cards} -> score={p2_score}"
        )
        if p1_score > p2_score:
            self.plain_log(f"WINNER: {p1.name} ({p1_score} > {p2_score})")
        elif p2_score > p1_score:
            self.plain_log(f"WINNER: {p2.name} ({p2_score} > {p1_score})")
        else:
            self.plain_log(f"WINNER: DRAW ({p1_score} = {p2_score})")
