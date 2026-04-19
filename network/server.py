"""Authoritative WebSocket server for real-time WikiDeck matches."""

from __future__ import annotations

import asyncio
import random
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any

import websockets

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from config import STARTING_HAND_SIZE
from core.card import Card
from core.card_factory import build_card_from_spec
from core.game_state import GameState
from core.player import Player
from data.db import get_cached_card, get_deck_cards, init_db
from network.protocol import (
    DISCARD_CARD,
    END_TURN,
    ERROR,
    EVENT,
    GAME_OVER,
    GAME_STATE,
    OPPONENT_DISCONNECTED,
    PLAY_CARD,
    ROLE,
    TARGET_SELECT,
    TARGETING,
    YOUR_TURN,
    decode,
    encode,
    make_message,
)
from network.sync import serialize_state

connections: dict[str, Any] = {}
game_state: GameState | None = None
active_player: str = "p1"
_action_lock: asyncio.Lock | None = None


def _log(text: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[net-server][{ts}] {text}", flush=True)


def _clone_card(card: Card) -> Card:
    return Card(
        title=card.title,
        hp=card.hp,
        max_hp=getattr(card, "max_hp", card.hp),
        base_score=card.base_score,
        theme=card.theme,
        rarity=card.rarity,
        description=card.description,
        extract=card.extract,
        image=card.image,
        ability_text=card.ability_text,
        ability_trigger=card.ability_trigger,
        effect_type=getattr(card, "effect_type", "NONE"),
        ability_value=int(getattr(card, "ability_value", 0) or 0),
        statuses=set(getattr(card, "statuses", set()) or set()),
        silenced_turns=int(getattr(card, "silenced_turns", 0) or 0),
        on_play=card.on_play,
        on_death=card.on_death,
    )


def _build_base_cards_from_deck() -> list[Card]:
    init_db()
    base_cards: list[Card] = []
    for entry in get_deck_cards():
        spec = get_cached_card(entry["title"], entry["rarity"])
        if spec is None:
            continue
        for _ in range(int(entry["count"])):
            base_cards.append(build_card_from_spec(spec))
    if not base_cards:
        raise RuntimeError("Active deck is empty. Build a deck before hosting.")
    return base_cards


def _make_shuffled_deck(base_cards: list[Card]) -> list[Card]:
    deck = [_clone_card(card) for card in base_cards]
    random.shuffle(deck)
    return deck


class ServerGameState(GameState):
    _event_hook = None

    def set_event_hook(self, hook) -> None:
        self._event_hook = hook

    def log_event(self, message: str) -> None:
        super().log_event(message)
        text = (message or "").strip()
        if text and callable(self._event_hook):
            self._event_hook(text)


def initialize_game() -> GameState:
    base_cards = _build_base_cards_from_deck()
    p1 = Player(name="P1", deck=_make_shuffled_deck(base_cards))
    p2 = Player(name="P2", deck=_make_shuffled_deck(base_cards))
    p1.draw_starting_hand(STARTING_HAND_SIZE)
    p2.draw_starting_hand(STARTING_HAND_SIZE)
    game = ServerGameState(players=[p1, p2], active_idx=0, verbose_terminal_logs=True)
    game.set_event_hook(lambda text: asyncio.create_task(broadcast_event(text)))
    game.start_match()
    _log("Game initialized.")
    return game


def _player_for_role(role: str) -> Player:
    assert game_state is not None
    return game_state.players[0] if role == "p1" else game_state.players[1]


def _role_for_player(player: Player) -> str:
    assert game_state is not None
    return "p1" if game_state.players[0] is player else "p2"


def _card_id(card: Card) -> int:
    return int(id(card))


def _find_in_cards(cards: list[Card], data: dict[str, Any]) -> Card | None:
    wanted_id = int(data.get("card_id", 0) or 0)
    wanted_title = str(data.get("card_title", "") or "")
    if wanted_id:
        for card in cards:
            if _card_id(card) == wanted_id:
                return card
    if wanted_title:
        for card in cards:
            if card.title == wanted_title:
                return card
    return None


async def _send(role: str, message: dict[str, Any]) -> None:
    websocket = connections.get(role)
    if websocket is None:
        return
    try:
        payload = encode(message)
        await websocket.send(payload)
        _log(f"TX->{role} {message['type']} {message.get('data', {})}")
    except Exception as exc:
        _log(f"Failed TX->{role}: {exc!r}")


async def _broadcast(message: dict[str, Any]) -> None:
    if not connections:
        return
    await asyncio.gather(*[_send(role, message) for role in list(connections.keys())], return_exceptions=True)


async def broadcast_state() -> None:
    if game_state is None:
        return
    payload = make_message(GAME_STATE, serialize_state(game_state))
    await _broadcast(payload)


async def broadcast_event(text: str) -> None:
    await _broadcast(make_message(EVENT, {"text": text}))


async def _send_targeting_prompt() -> None:
    if game_state is None or not game_state.is_targeting_active():
        return
    state = serialize_state(game_state).get("targeting", {})
    owner = state.get("owner") or active_player
    await _send(str(owner), make_message(TARGETING, state))


async def _send_your_turn() -> None:
    await _send(active_player, make_message(YOUR_TURN, {"player": active_player}))


async def _send_game_over() -> None:
    if game_state is None:
        return
    p1, p2 = game_state.players
    p1_score = game_state.score_for(p1)
    p2_score = game_state.score_for(p2)
    winner = "draw"
    if p1_score > p2_score:
        winner = "p1"
    elif p2_score > p1_score:
        winner = "p2"
    await _broadcast(
        make_message(
            GAME_OVER,
            {"winner": winner, "p1_score": p1_score, "p2_score": p2_score},
        )
    )


async def start_game() -> None:
    global game_state, active_player
    game_state = initialize_game()
    active_player = "p1"
    _log("Starting game and broadcasting initial state.")
    await broadcast_state()
    await _send_your_turn()


async def _reject(role: str, text: str) -> None:
    _log(f"REJECT {role}: {text}")
    await _send(role, make_message(ERROR, {"text": text}))


def _is_action_allowed(role: str, action: str) -> tuple[bool, str]:
    if game_state is None:
        return False, "Game has not started yet."
    if action == TARGET_SELECT and game_state.is_targeting_active():
        owner = game_state.targeting_state.get("owner")
        if isinstance(owner, Player):
            expected = _role_for_player(owner)
        else:
            expected = active_player
        if role != expected:
            return False, "Not your turn"
        return True, ""
    if role != active_player:
        return False, "Not your turn"
    return True, ""


async def handle_action(role: str, message: dict[str, Any]) -> None:
    global active_player
    assert _action_lock is not None
    async with _action_lock:
        action = str(message.get("type", ""))
        data = dict(message.get("data", {}))
        _log(f"RX<-{role} action={action} data={data}")
        allowed, reason = _is_action_allowed(role, action)
        if not allowed:
            await _reject(role, reason)
            return
        assert game_state is not None
        player = _player_for_role(role)
        if action == PLAY_CARD:
            if game_state.is_targeting_active():
                await _reject(role, "Resolve targeting first.")
                return
            card = _find_in_cards(player.hand, data)
            if card is None:
                await _reject(role, "Card not found in hand.")
                return
            if not game_state.try_play(card):
                await _reject(role, "Cannot play this card right now.")
                return
        elif action == DISCARD_CARD:
            if game_state.is_targeting_active():
                await _reject(role, "Resolve targeting first.")
                return
            card = _find_in_cards(player.hand, data)
            if card is None:
                await _reject(role, "Card not found in hand.")
                return
            if not game_state.try_discard(card):
                await _reject(role, "Cannot discard this card right now.")
                return
        elif action == END_TURN:
            if game_state.is_targeting_active():
                await _reject(role, "Resolve targeting first.")
                return
            if not game_state.can_end_turn():
                await _reject(role, "Cannot end turn yet.")
                return
            game_state.end_turn()
            active_player = "p1" if game_state.active_idx == 0 else "p2"
        elif action == TARGET_SELECT:
            if not game_state.is_targeting_active():
                await _reject(role, "No targeting request is active.")
                return
            valid = list(game_state.targeting_state.get("valid_targets", []))
            target = _find_in_cards(valid, data)
            if target is None:
                await _reject(role, "Selected card is not a valid target.")
                return
            if not game_state.resolve_targeting(target):
                await _reject(role, "Target selection was rejected.")
                return
            active_player = "p1" if game_state.active_idx == 0 else "p2"
        else:
            await _reject(role, f"Unknown action: {action}")
            return

        await broadcast_state()
        if game_state.phase.value == "GAME_OVER":
            await _send_game_over()
            return
        if game_state.is_targeting_active():
            await _send_targeting_prompt()
            return
        await _send_your_turn()


async def _notify_opponent_disconnected(role: str) -> None:
    other = "p2" if role == "p1" else "p1"
    if other in connections:
        await _send(other, make_message(OPPONENT_DISCONNECTED, {}))


async def handler(websocket) -> None:
    global _action_lock
    if _action_lock is None:
        _action_lock = asyncio.Lock()

    if "p1" not in connections:
        role = "p1"
    elif "p2" not in connections:
        role = "p2"
    else:
        await websocket.send(encode(make_message(ERROR, {"text": "Game full"})))
        _log("Rejected extra connection: game full.")
        return

    connections[role] = websocket
    _log(f"Connected {role}. peers={list(connections.keys())}")
    await _send(role, make_message(ROLE, {"role": role}))

    if game_state is not None:
        await _send(role, make_message(GAME_STATE, serialize_state(game_state)))
        await _send(role, make_message(YOUR_TURN, {"player": active_player}))
    elif len(connections) == 2:
        await start_game()
    else:
        await _send(role, make_message(EVENT, {"text": "Waiting for opponent..."}))

    try:
        async for raw in websocket:
            try:
                data = decode(raw)
            except Exception as exc:
                await _reject(role, f"Invalid JSON payload: {exc}")
                continue
            await handle_action(role, data)
    except websockets.exceptions.ConnectionClosed:
        _log(f"{role} disconnected.")
    finally:
        if role in connections and connections[role] is websocket:
            del connections[role]
        await _notify_opponent_disconnected(role)
        _reset_match_if_needed()


def _reset_match_if_needed() -> None:
    global game_state, active_player
    if len(connections) < 2:
        game_state = None
        active_player = "p1"
        _log("Match state reset (waiting for two players).")


@dataclass
class ServerHandle:
    port: int
    host: str
    thread: threading.Thread
    _stop_flag: threading.Event

    def stop(self) -> None:
        self._stop_flag.set()
        _log("Stop requested.")


def start_background_server(host: str = "0.0.0.0", ports: tuple[int, ...] = (8765, 8766, 8767)) -> ServerHandle:
    ready: "queue.Queue[tuple[str, int | None, str | None]]"
    import queue

    ready = queue.Queue()
    stop_flag = threading.Event()

    def runner() -> None:
        asyncio.run(_thread_main(host, ports, ready, stop_flag))

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    status, port, error = ready.get(timeout=10)
    if status != "ok" or port is None:
        raise RuntimeError(error or "Failed to start server.")
    _log(f"Background server started on {host}:{port}")
    return ServerHandle(port=port, host=host, thread=thread, _stop_flag=stop_flag)


async def _thread_main(
    host: str,
    ports: tuple[int, ...],
    ready,
    stop_flag: threading.Event,
) -> None:
    server = None
    chosen_port = None
    for port in ports:
        try:
            server = await websockets.serve(handler, host, port)
            chosen_port = port
            ready.put(("ok", port, None))
            _log(f"Server listening on {host}:{port}")
            break
        except OSError as exc:
            _log(f"Port {port} unavailable: {exc}")
    if server is None or chosen_port is None:
        ready.put(("error", None, f"No available ports in {list(ports)}"))
        return
    try:
        while not stop_flag.is_set():
            await asyncio.sleep(0.1)
    finally:
        _log(f"Stopping server on {host}:{chosen_port}")
        server.close()
        await server.wait_closed()
        connections.clear()
        _reset_match_if_needed()


async def main() -> None:
    ready = asyncio.Event()
    stop_flag = threading.Event()

    async def notify_ready() -> None:
        ready.set()

    server = None
    for port in (8765, 8766, 8767):
        try:
            server = await websockets.serve(handler, "0.0.0.0", port)
            _log(f"WikiDeck server running on port {port}")
            break
        except OSError as exc:
            _log(f"Port {port} unavailable: {exc}")
    if server is None:
        raise RuntimeError("Could not bind to ports 8765-8767")
    await notify_ready()
    try:
        await asyncio.Future()
    finally:
        stop_flag.set()
        server.close()
        await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
