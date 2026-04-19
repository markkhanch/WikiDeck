"""Booster and shop backend with async pack generation."""

from __future__ import annotations

import json
import random
import sqlite3
import threading
import time
from typing import Any

from config import DB_PATH
from data.db import (
    add_to_collection,
    add_to_deck,
    deck_size,
    get_cached_card,
    save_card,
)
from data.ollama_gen import apply_diversity, generate_card_spec, get_article_from_pool

PACK_READY_SECONDS = 0.0

PACK_TYPES: dict[str, dict[str, Any]] = {
    "basic": {
        "price": 50,
        "size": 5,
        "weights": {"COMMON": 60, "UNCOMMON": 30, "RARE": 8, "EPIC": 2, "LEGENDARY": 0},
    },
    "premium": {
        "price": 150,
        "size": 5,
        "weights": {"COMMON": 30, "UNCOMMON": 35, "RARE": 25, "EPIC": 8, "LEGENDARY": 2},
    },
    "epic": {
        "price": 300,
        "size": 5,
        "weights": {"COMMON": 10, "UNCOMMON": 20, "RARE": 35, "EPIC": 30, "LEGENDARY": 5},
    },
    "legendary": {
        "price": 600,
        "size": 5,
        "weights": {"COMMON": 0, "UNCOMMON": 5, "RARE": 20, "EPIC": 40, "LEGENDARY": 35},
    },
}

PACK_DISPLAY_NAMES = {
    "basic": "Basic Pack",
    "premium": "Premium Pack",
    "epic": "Epic Pack",
    "legendary": "Legendary Pack",
}

SINGLE_PRICES = {
    "COMMON": 30,
    "UNCOMMON": 75,
    "RARE": 150,
    "EPIC": 400,
    "LEGENDARY": 1000,
}

SINGLE_RARITY_WEIGHTS = {"COMMON": 55, "UNCOMMON": 25, "RARE": 13, "EPIC": 6, "LEGENDARY": 1}
_GENERATION_LOCK = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _ensure_shop_tables() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_packs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pack_type TEXT NOT NULL,
                purchased_at REAL NOT NULL,
                ready_at REAL NOT NULL,
                status TEXT DEFAULT 'generating',
                cards_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shop_singles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_title TEXT NOT NULL,
                card_rarity TEXT NOT NULL,
                price INTEGER NOT NULL,
                added_at REAL NOT NULL
            )
            """
        )
        conn.commit()


def pick_rarity_weighted(pack_type: str) -> str:
    weights = PACK_TYPES[pack_type]["weights"]
    rarities = list(weights.keys())
    w = list(weights.values())
    return random.choices(rarities, weights=w, k=1)[0]


def _safe_load_cards(cards_json: str | None) -> list[dict]:
    if not cards_json:
        return []
    try:
        value = json.loads(cards_json)
    except json.JSONDecodeError:
        return []
    if isinstance(value, list):
        return value
    return []


def _save_pending_cards(pack_id: int, cards: list[dict], status: str = "generating") -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE pending_packs SET cards_json = ?, status = ? WHERE id = ?",
            (json.dumps(cards, ensure_ascii=False), status, pack_id),
        )
        conn.commit()


def _generate_pack_cards(pack_type: str, on_progress=None, pack_size: int | None = None) -> list[dict]:
    if pack_type not in PACK_TYPES:
        raise ValueError(f"Unknown pack type: {pack_type}")

    pack_size = int(pack_size or PACK_TYPES[pack_type]["size"])
    cards: list[dict] = []
    seen: set[tuple[str, str]] = set()
    attempts = 0
    max_attempts = pack_size * 20
    diversity = {"effects": {}, "triggers": {}, "target": pack_size}

    while len(cards) < pack_size:
        attempts += 1
        if attempts > max_attempts:
            raise RuntimeError(f"Could not generate enough cards for {pack_type} pack")

        rarity = pick_rarity_weighted(pack_type)
        title, summary, _ignored_rarity = get_article_from_pool(diversity=diversity, pack_rarity=rarity)
        key = (title, rarity)
        if key in seen:
            continue

        spec = generate_card_spec(title, summary, rarity, diversity=diversity)
        cards.append(spec)
        seen.add(key)
        apply_diversity(diversity, spec)

        if on_progress is not None:
            on_progress(cards)

    return cards


def _generate_in_background(pack_id: int, pack_type: str) -> None:
    cards: list[dict] = []

    def _progress(current_cards: list[dict]) -> None:
        nonlocal cards
        cards = list(current_cards)
        _save_pending_cards(pack_id, cards, status="generating")

    try:
        with _GENERATION_LOCK:
            cards = _generate_pack_cards(pack_type, on_progress=_progress)
        _save_pending_cards(pack_id, cards, status="ready")
    except Exception as exc:
        print(f"[shop] pack #{pack_id} generation failed: {exc}", flush=True)
        _save_pending_cards(pack_id, cards, status="ready" if cards else "generating")


def purchase_pack(pack_type: str) -> int:
    if pack_type not in PACK_TYPES:
        raise ValueError(f"Unknown pack type: {pack_type}")

    _ensure_shop_tables()
    now = time.time()
    ready_at = now + PACK_READY_SECONDS

    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO pending_packs (pack_type, purchased_at, ready_at, status, cards_json)
            VALUES (?, ?, ?, 'generating', '[]')
            """,
            (pack_type, now, ready_at),
        )
        pack_id = int(cur.lastrowid)
        conn.commit()

    threading.Thread(
        target=_generate_in_background,
        args=(pack_id, pack_type),
        daemon=True,
    ).start()
    return pack_id


def get_pending_packs() -> list[dict]:
    _ensure_shop_tables()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, pack_type, purchased_at, ready_at, status, cards_json
            FROM pending_packs
            WHERE status != 'opened'
            ORDER BY purchased_at DESC
            """
        ).fetchall()

    result: list[dict] = []
    for row in rows:
        cards = _safe_load_cards(row["cards_json"])
        pack_type = str(row["pack_type"])
        pack_size = int(PACK_TYPES.get(pack_type, {"size": 5})["size"])
        ready_at = float(row["ready_at"])
        is_ready_for_open = row["status"] == "ready"
        result.append(
            {
                "id": int(row["id"]),
                "pack_type": pack_type,
                "pack_name": PACK_DISPLAY_NAMES.get(pack_type, pack_type.title()),
                "purchased_at": float(row["purchased_at"]),
                "ready_at": ready_at,
                "status": str(row["status"]),
                "cards": cards,
                "generated_count": len(cards),
                "pack_size": pack_size,
                "seconds_left": 0,
                "can_open": is_ready_for_open,
            }
        )
    return result


def open_pack(pack_id: int) -> list[dict] | None:
    _ensure_shop_tables()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, status, ready_at, cards_json
            FROM pending_packs
            WHERE id = ?
            """,
            (pack_id,),
        ).fetchone()

        if row is None:
            return None
        if row["status"] == "opened":
            return None
        if row["status"] != "ready":
            return None

        cards = _safe_load_cards(row["cards_json"])
        if not cards:
            return None

        conn.execute("UPDATE pending_packs SET status = 'opened' WHERE id = ?", (pack_id,))
        conn.commit()

    add_pack_to_collection_and_deck(cards)
    return cards


def _pick_single_rarity() -> str:
    rarities = list(SINGLE_RARITY_WEIGHTS.keys())
    weights = list(SINGLE_RARITY_WEIGHTS.values())
    return random.choices(rarities, weights=weights, k=1)[0]


def _generate_single_spec() -> dict:
    rarity = _pick_single_rarity()
    title, summary, _ignored_rarity = get_article_from_pool()
    spec = generate_card_spec(title, summary, rarity)
    return spec


def _insert_single(spec: dict) -> None:
    rarity = str(spec.get("rarity", "COMMON")).upper()
    price = int(SINGLE_PRICES.get(rarity, SINGLE_PRICES["COMMON"]))
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO shop_singles (card_title, card_rarity, price, added_at)
            VALUES (?, ?, ?, ?)
            """,
            (spec["title"], rarity, price, time.time()),
        )
        conn.commit()


def _generate_single_in_background() -> None:
    try:
        with _GENERATION_LOCK:
            spec = _generate_single_spec()
        _insert_single(spec)
    except Exception as exc:
        print(f"[shop] single card generation failed: {exc}", flush=True)


def ensure_shop_singles(min_count: int = 2) -> None:
    _ensure_shop_tables()
    with _connect() as conn:
        current = int(conn.execute("SELECT COUNT(*) FROM shop_singles").fetchone()[0])
    missing = max(0, min_count - current)
    for _ in range(missing):
        spec = _generate_single_spec()
        _insert_single(spec)


def get_shop_singles() -> list[dict]:
    _ensure_shop_tables()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, card_title, card_rarity, price, added_at
            FROM shop_singles
            ORDER BY added_at ASC
            """
        ).fetchall()

    result: list[dict] = []
    for row in rows:
        title = str(row["card_title"])
        rarity = str(row["card_rarity"])
        spec = get_cached_card(title, rarity)
        result.append(
            {
                "id": int(row["id"]),
                "title": title,
                "rarity": rarity,
                "price": int(row["price"]),
                "added_at": float(row["added_at"]),
                "spec": spec,
            }
        )
    return result


def buy_single_card(single_id: int) -> dict | None:
    _ensure_shop_tables()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, card_title, card_rarity, price
            FROM shop_singles
            WHERE id = ?
            """,
            (single_id,),
        ).fetchone()
        if row is None:
            return None

        conn.execute("DELETE FROM shop_singles WHERE id = ?", (single_id,))
        conn.commit()

    title = str(row["card_title"])
    rarity = str(row["card_rarity"])
    add_to_collection(title, rarity, 1)
    if deck_size() < 20:
        add_to_deck(title, rarity, 1)

    threading.Thread(target=_generate_single_in_background, daemon=True).start()
    return {"id": int(row["id"]), "title": title, "rarity": rarity, "price": int(row["price"])}


def open_random_pack(pack_size: int = 5, on_progress=None) -> list[dict]:
    def _progress(current_cards: list[dict]) -> None:
        if on_progress is None or not current_cards:
            return
        on_progress(current_cards[-1], len(current_cards), pack_size)

    return _generate_pack_cards("basic", on_progress=_progress, pack_size=pack_size)


def add_pack_to_collection_and_deck(cards: list[dict], auto_fill_target: int = 20) -> None:
    if not cards:
        return

    for spec in cards:
        save_card(spec)
        title = spec["title"]
        rarity = spec["rarity"]
        add_to_collection(title, rarity, 1)

    if deck_size() >= auto_fill_target:
        return

    for spec in cards:
        if deck_size() >= auto_fill_target:
            break
        add_to_deck(spec["title"], spec["rarity"], 1)
