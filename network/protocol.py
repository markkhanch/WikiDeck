"""WebSocket message protocol helpers for WikiDeck networking."""

from __future__ import annotations

import json
from typing import Any

PLAY_CARD = "play_card"
END_TURN = "end_turn"
TARGET_SELECT = "target_select"
DISCARD_CARD = "discard_card"
ORDER_CARD = "order_card"

ROLE = "role"
GAME_STATE = "game_state"
YOUR_TURN = "your_turn"
TARGETING = "targeting"
EVENT = "event"
GAME_OVER = "game_over"
ERROR = "error"
OPPONENT_DISCONNECTED = "opponent_disconnected"
CONNECTION_STATUS = "connection_status"


def make_message(msg_type: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"type": msg_type, "data": data or {}}


def encode(message: dict[str, Any]) -> str:
    return json.dumps(message, ensure_ascii=False)


def decode(raw: str) -> dict[str, Any]:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Protocol payload must be a JSON object.")
    if "type" not in payload:
        raise ValueError("Protocol payload missing 'type'.")
    data = payload.get("data", {})
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("Protocol payload 'data' must be an object.")
    return {"type": str(payload["type"]), "data": data}
