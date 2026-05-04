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
from data.settings_schema import (
    PACK_ORDER,
    PACK_TYPES_DEFAULT,
    RARITIES,
    SINGLE_PRICES_DEFAULT,
    SINGLE_RARITY_WEIGHTS_DEFAULT,
)
from data.settings_service import get_int

PACK_READY_SECONDS = 0.0

PACK_TYPES: dict[str, dict[str, Any]] = {
    key: {
        "price": int(value["price"]),
        "size": int(value["size"]),
        "weights": dict(value["weights"]),
    }
    for key, value in PACK_TYPES_DEFAULT.items()
}

PACK_DISPLAY_NAMES = {
    "basic": "Basic Pack",
    "premium": "Premium Pack",
    "epic": "Epic Pack",
    "legendary": "Legendary Pack",
}

SINGLE_PRICES = dict(SINGLE_PRICES_DEFAULT)
SINGLE_RARITY_WEIGHTS = dict(SINGLE_RARITY_WEIGHTS_DEFAULT)
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


def get_pack_types() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for pack in PACK_ORDER:
        defaults = PACK_TYPES_DEFAULT[pack]
        weights: dict[str, int] = {}
        for rarity in RARITIES:
            weights[rarity] = get_int(f"shop.pack.{pack}.weight.{rarity.lower()}")
        out[pack] = {
            "price": get_int(f"shop.pack.{pack}.price"),
            "size": get_int(f"shop.pack.{pack}.size"),
            "weights": weights,
        }
        if sum(weights.values()) <= 0:
            out[pack]["weights"] = dict(defaults["weights"])
    return out


def get_single_prices() -> dict[str, int]:
    return {rarity: get_int(f"shop.single.price.{rarity.lower()}") for rarity in RARITIES}


def get_single_rarity_weights() -> dict[str, int]:
    out = {rarity: get_int(f"shop.single.weight.{rarity.lower()}") for rarity in RARITIES}
    if sum(out.values()) <= 0:
        return dict(SINGLE_RARITY_WEIGHTS_DEFAULT)
    return out


def _deck_target() -> int:
    return get_int("gameplay.deck_target")


def pick_rarity_weighted(pack_type: str) -> str:
    pack_types = get_pack_types()
    weights = pack_types[pack_type]["weights"]
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
    pack_types = get_pack_types()
    if pack_type not in pack_types:
        raise ValueError(f"Unknown pack type: {pack_type}")

    pack_size = int(pack_size or pack_types[pack_type]["size"])
    cards: list[dict] = []
    used_source_titles: set[str] = set()
    used_card_titles: set[str] = set()
    attempts = 0
    max_attempts = pack_size * 20
    diversity = {"effects": {}, "triggers": {}, "target": pack_size}

    while len(cards) < pack_size:
        attempts += 1
        if attempts > max_attempts:
            raise RuntimeError(f"Could not generate enough cards for {pack_type} pack")

        rarity = pick_rarity_weighted(pack_type)
        title, summary, _ignored_rarity = get_article_from_pool(diversity=diversity, pack_rarity=rarity)
        if title in used_source_titles:
            continue
        used_source_titles.add(title)

        spec = generate_card_spec(title, summary, rarity, diversity=diversity)
        final_title = str(spec.get("title", title) or title)
        if final_title in used_card_titles:
            continue

        cards.append(spec)
        used_card_titles.add(final_title)
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
        _save_pending_cards(pack_id, cards, status="ready" if cards else "error")


def purchase_pack(pack_type: str) -> int:
    if pack_type not in get_pack_types():
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
    pack_types = get_pack_types()
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
        pack_size = int(pack_types.get(pack_type, {"size": 5})["size"])
        ready_at = float(row["ready_at"])
        is_ready_for_open = row["status"] == "ready" and bool(cards)
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
    single_weights = get_single_rarity_weights()
    rarities = list(single_weights.keys())
    weights = list(single_weights.values())
    return random.choices(rarities, weights=weights, k=1)[0]


def _generate_single_spec() -> dict:
    rarity = _pick_single_rarity()
    title, summary, _ignored_rarity = get_article_from_pool()
    spec = generate_card_spec(title, summary, rarity)
    return spec


def _insert_single(spec: dict) -> None:
    single_prices = get_single_prices()
    rarity = str(spec.get("rarity", "COMMON")).upper()
    price = int(single_prices.get(rarity, single_prices["COMMON"]))
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
        try:
            spec = _generate_single_spec()
            _insert_single(spec)
        except Exception as exc:
            print(f"[shop] ensure singles failed: {exc}", flush=True)
            break


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
    if deck_size() < _deck_target():
        add_to_deck(title, rarity, 1)

    threading.Thread(target=_generate_single_in_background, daemon=True).start()
    return {"id": int(row["id"]), "title": title, "rarity": rarity, "price": int(row["price"])}


def open_random_pack(pack_size: int = 5, on_progress=None) -> list[dict]:
    def _progress(current_cards: list[dict]) -> None:
        if on_progress is None or not current_cards:
            return
        on_progress(current_cards[-1], len(current_cards), pack_size)

    return _generate_pack_cards("basic", on_progress=_progress, pack_size=pack_size)


def add_pack_to_collection_and_deck(cards: list[dict], auto_fill_target: int | None = None) -> None:
    if not cards:
        return
    target = int(_deck_target() if auto_fill_target is None else auto_fill_target)

    for spec in cards:
        save_card(spec)
        title = spec["title"]
        rarity = spec["rarity"]
        add_to_collection(title, rarity, 1)

    if deck_size() >= target:
        return

    for spec in cards:
        if deck_size() >= target:
            break
        add_to_deck(spec["title"], spec["rarity"], 1)
