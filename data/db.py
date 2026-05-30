"""Local cache layer — sits between the game and Wikipedia.

Two caches, different backends because the data shape differs:
 - Article text → SQLite (`articles` table). Cheap rows, fast lookup.
 - Card images → plain PNG files in CARD_IMAGES_DIR. Pygame can load them
   straight from disk with .convert_alpha(); no point shoving bytes in SQLite.

Both caches are write-through: miss → fetch from Wikipedia → save → return.
Network failures fall through silently so the game can run offline once the
starter deck is warmed up.
"""
import io
import os
import re
import sqlite3
from urllib.parse import urlparse
from typing import Optional

import pygame
import requests

from config import CARD_IMAGES_DIR, DB_PATH
from data.wikipedia import HEADERS as _WIKI_HEADERS
from data.wikipedia import TIMEOUT as _WIKI_TIMEOUT
from data.wikipedia import fetch_media_image_url, get_article, load_card_image

try:
    from PIL import Image as _PILImage
except ImportError:  # pragma: no cover
    _PILImage = None


_SAFE_CHARS = re.compile(r"[^A-Za-z0-9_-]+")
_IMAGE_EXTS = (".jpg", ".jpeg", ".png")


def _sanitize(title: str) -> str:
    """Turn a Wikipedia title into a safe filename stem."""
    return _SAFE_CHARS.sub("_", title).strip("_") or "untitled"


def _is_supported_image_url(url: Optional[str]) -> bool:
    if not url:
        return False
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in _IMAGE_EXTS)


# ---- SQLite ----

def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                title         TEXT PRIMARY KEY,
                display_title TEXT NOT NULL,
                description   TEXT NOT NULL,
                extract       TEXT NOT NULL,
                thumbnail_url TEXT,
                fetched_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS generated_cards (
                title         TEXT PRIMARY KEY,
                theme         TEXT NOT NULL,
                epoch         TEXT NOT NULL,
                rarity        TEXT NOT NULL,
                trigger       TEXT NOT NULL,
                trigger_value INTEGER NOT NULL,
                effect_type   TEXT NOT NULL,
                ability_text  TEXT,
                ability_value INTEGER NOT NULL,
                nemesis       TEXT,
                hp            INTEGER NOT NULL,
                base_score    INTEGER NOT NULL,
                generated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cards (
                title         TEXT NOT NULL,
                rarity        TEXT NOT NULL,
                theme         TEXT NOT NULL,
                epoch         TEXT NOT NULL,
                trigger       TEXT NOT NULL,
                trigger_value INTEGER NOT NULL,
                effect_type   TEXT NOT NULL,
                ability_text  TEXT,
                ability_value INTEGER NOT NULL,
                nemesis       TEXT,
                hp            INTEGER NOT NULL,
                base_score    INTEGER NOT NULL,
                archetype     TEXT,
                rationale     TEXT,
                generated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (title, rarity)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS collection (
                title  TEXT NOT NULL,
                rarity TEXT NOT NULL,
                count  INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (title, rarity)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS decks (
                id        TEXT PRIMARY KEY,
                name      TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS deck_cards (
                deck_id TEXT NOT NULL,
                title   TEXT NOT NULL,
                rarity  TEXT NOT NULL,
                count   INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (deck_id, title, rarity)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # One-time migration from generated_cards → cards (title+rarity)
        conn.execute(
            """
            INSERT OR IGNORE INTO cards
            (title, rarity, theme, epoch, trigger, trigger_value, effect_type,
             ability_text, ability_value, nemesis, hp, base_score, generated_at)
            SELECT title, rarity, theme, epoch, trigger, trigger_value, effect_type,
                   ability_text, ability_value, nemesis, hp, base_score, generated_at
            FROM generated_cards
            """
        )

        # Add archetype + rationale columns on older databases.
        existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(cards)").fetchall()}
        if "archetype" not in existing_cols:
            conn.execute("ALTER TABLE cards ADD COLUMN archetype TEXT")
        if "rationale" not in existing_cols:
            conn.execute("ALTER TABLE cards ADD COLUMN rationale TEXT")

        # Ensure a single active deck exists
        row = conn.execute("SELECT id FROM decks WHERE is_active = 1 LIMIT 1").fetchone()
        if row is None:
            conn.execute(
                "INSERT OR IGNORE INTO decks (id, name, is_active) VALUES ('default', 'Active Deck', 1)"
            )
        conn.execute("DELETE FROM collection WHERE count <= 0")
        conn.execute("DELETE FROM deck_cards WHERE count <= 0")


def _get_article_from_db(title: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT display_title, description, extract, thumbnail_url "
            "FROM articles WHERE title = ?",
            (title,),
        ).fetchone()
    if row is None:
        return None
    return {
        "title":       row["display_title"],
        "description": row["description"],
        "extract":     row["extract"],
        "thumbnail":   row["thumbnail_url"],
    }


def get_cached_article(title: str) -> Optional[dict]:
    """Return cached article data only (no network fetch)."""
    return _get_article_from_db(title)


def _save_article(title: str, data: dict) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO articles "
            "(title, display_title, description, extract, thumbnail_url) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                title,
                data.get("title", title),
                data.get("description", ""),
                data.get("extract", ""),
                data.get("thumbnail"),
            ),
        )


def get_or_fetch_article(title: str) -> Optional[dict]:
    """Check SQLite, fall back to Wikipedia. Returns None if both miss."""
    cached = _get_article_from_db(title)
    if cached is not None:
        if not _is_supported_image_url(cached.get("thumbnail")):
            data = get_article(title)
            if data is not None:
                _save_article(title, data)
                return data
        return cached
    data = get_article(title)
    if data is None:
        return None
    _save_article(title, data)
    return data


# ---- Image cache ----

def get_or_fetch_image(title: str, url: Optional[str]) -> Optional[pygame.Surface]:
    """Check disk, fall back to download. Returns None on any failure.

    Keyed by title — one image per article. If the URL changes upstream,
    delete the PNG to force a re-fetch.
    """
    os.makedirs(CARD_IMAGES_DIR, exist_ok=True)
    path = os.path.join(CARD_IMAGES_DIR, f"{_sanitize(title)}.png")

    if os.path.isfile(path):
        try:
            surface = pygame.image.load(path)
            try:
                return surface.convert_alpha()
            except pygame.error:
                return surface
        except pygame.error:
            pass  # corrupt file → fall through and re-download

    if not url:
        return None

    surface = load_card_image(url)
    if surface is None:
        return None

    try:
        pygame.image.save(surface, path)
    except pygame.error:
        pass  # cache write failed; still return the in-memory surface
    return surface


def get_cached_image(title: str) -> Optional[pygame.Surface]:
    """Return cached card image only (no network fetch)."""
    path = os.path.join(CARD_IMAGES_DIR, f"{_sanitize(title)}.png")
    if not os.path.isfile(path):
        return None
    try:
        surface = pygame.image.load(path)
        try:
            return surface.convert_alpha()
        except pygame.error:
            return surface
    except pygame.error:
        return None


def is_card_image_cached(title: str) -> bool:
    """True iff a PNG for this title already exists in the image cache."""
    if not title:
        return False
    path = os.path.join(CARD_IMAGES_DIR, f"{_sanitize(title)}.png")
    return os.path.isfile(path)


def _fetch_image_bytes(url: str) -> Optional[bytes]:
    """Download image bytes with retry/backoff on 429/5xx. Returns None on failure."""
    import time as _time

    for attempt in range(5):
        try:
            response = requests.get(url, headers=_WIKI_HEADERS, timeout=_WIKI_TIMEOUT)
        except requests.RequestException:
            _time.sleep(0.5 * (attempt + 1))
            continue
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            try:
                delay = int(retry_after) if retry_after else 1
            except ValueError:
                delay = 1
            _time.sleep(min(6, max(1, delay)) * (attempt + 1))
            continue
        if response.status_code >= 500:
            _time.sleep(0.8 * (attempt + 1))
            continue
        if response.status_code != 200:
            return None
        ctype = response.headers.get("Content-Type", "").lower()
        if not ctype.startswith("image/"):
            return None
        if not response.content:
            return None
        return response.content
    return None


def _download_image_to_disk(title: str, url: Optional[str]) -> bool:
    """Download an image and write it as PNG to the card image cache.

    Runs without pygame (thread-safe). Returns True if a file is on disk after
    the call — either because it already existed or because the download
    succeeded.
    """
    if not title:
        return False
    os.makedirs(CARD_IMAGES_DIR, exist_ok=True)
    path = os.path.join(CARD_IMAGES_DIR, f"{_sanitize(title)}.png")
    if os.path.isfile(path):
        return True
    if not url:
        return False
    data = _fetch_image_bytes(url)
    if not data:
        return False
    if _PILImage is not None:
        try:
            img = _PILImage.open(io.BytesIO(data))
            img.load()
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            img.save(path, format="PNG")
            return True
        except Exception:
            pass
    try:
        with open(path, "wb") as fh:
            fh.write(data)
        return True
    except OSError:
        return False


def prefetch_card_assets(title: str) -> None:
    """Warm article + image cache so later allow_fetch=False builds find them on disk."""
    data = get_or_fetch_article(title)
    if data is None:
        media_url = fetch_media_image_url(title)
        _download_image_to_disk(title, media_url)
        return
    resolved_title = data["title"]
    thumb = data.get("thumbnail")
    if _download_image_to_disk(resolved_title, thumb):
        return
    media_url = fetch_media_image_url(resolved_title)
    _download_image_to_disk(resolved_title, media_url)


# ---- Generated card cache ----

def _normalize_effect_for_strengthless_mode(effect_type: str) -> str:
    normalized = str(effect_type or "NONE").strip().upper()
    if normalized == "BOOST":
        return "VITALITY"
    if normalized == "DRAIN":
        return "DAMAGE"
    return normalized or "NONE"


def _rewrite_legacy_strength_text(effect_type: str, ability_text: str, ability_value: int) -> str:
    text = str(ability_text or "").strip()
    if effect_type == "VITALITY":
        if not text or re.search(r"\bboost\b", text, re.IGNORECASE):
            return f"Give this card Vitality for {max(1, int(ability_value or 0))} turns."
    if effect_type == "DAMAGE":
        if not text or re.search(r"\bdrain\b", text, re.IGNORECASE):
            return f"Deal {max(1, int(ability_value or 0))} damage to one enemy card."
    return text


def _row_to_card_spec(row: sqlite3.Row, *, title_override: str | None = None) -> dict:
    raw_effect = str(row["effect_type"] or "NONE")
    effect_type = _normalize_effect_for_strengthless_mode(raw_effect)
    base_value = int(row["ability_value"] or 0)
    ability_value = max(1, base_value) if raw_effect.upper() in {"BOOST", "DRAIN"} else base_value
    keys = set(row.keys())
    archetype = (row["archetype"] if "archetype" in keys else "") or ""
    rationale = (row["rationale"] if "rationale" in keys else "") or ""
    return {
        "title": title_override or row["title"],
        "theme": row["theme"],
        "epoch": row["epoch"],
        "rarity": row["rarity"],
        "trigger": row["trigger"],
        "trigger_value": row["trigger_value"],
        "effect_type": effect_type,
        "ability_text": _rewrite_legacy_strength_text(effect_type, row["ability_text"] or "", ability_value),
        "ability_value": ability_value,
        "nemesis": row["nemesis"],
        "hp": row["hp"],
        "archetype": archetype,
        "rationale": rationale,
    }


def get_cached_card(title: str, rarity: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT title, theme, epoch, rarity, trigger, trigger_value, effect_type,
                   ability_text, ability_value, nemesis, hp, archetype, rationale
            FROM cards
            WHERE title = ? AND rarity = ?
            """,
            (title, rarity),
        ).fetchone()
    if row is None:
        return None
    return _row_to_card_spec(row, title_override=title)


def save_card(card: dict) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO cards
            (title, rarity, theme, epoch, trigger, trigger_value, effect_type,
             ability_text, ability_value, nemesis, hp, base_score,
             archetype, rationale)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                card.get("title", ""),
                card.get("rarity", "COMMON"),
                card.get("theme", "CONCEPTS"),
                card.get("epoch", "TIMELESS"),
                card.get("trigger", "NO ABILITY"),
                int(card.get("trigger_value", 0)),
                card.get("effect_type", "NONE"),
                card.get("ability_text", ""),
                int(card.get("ability_value", 0)),
                card.get("nemesis"),
                int(card.get("hp", 1)),
                int(card.get("base_score", 0)),
                (card.get("archetype") or "") or None,
                (card.get("rationale") or "") or None,
            ),
        )


def get_effect_distribution() -> dict[str, int]:
    """Return effect_type -> count across all saved cards."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT effect_type, COUNT(*) AS n FROM cards GROUP BY effect_type"
        ).fetchall()
    return {str(r["effect_type"]): int(r["n"]) for r in rows}


def get_trigger_distribution() -> dict[str, int]:
    """Return trigger -> count across all saved cards."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT trigger, COUNT(*) AS n FROM cards GROUP BY trigger"
        ).fetchall()
    return {str(r["trigger"]): int(r["n"]) for r in rows}


def get_archetype_distribution() -> dict[str, int]:
    """Return archetype -> count across all saved cards (NULL → '')."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT COALESCE(archetype, '') AS a, COUNT(*) AS n FROM cards GROUP BY a"
        ).fetchall()
    return {str(r["a"]): int(r["n"]) for r in rows}


def get_active_deck_id() -> str:
    with _connect() as conn:
        row = conn.execute("SELECT id FROM decks WHERE is_active = 1 LIMIT 1").fetchone()
    return row["id"] if row else "default"


def add_to_collection(title: str, rarity: str, count: int = 1) -> None:
    if count <= 0:
        raise ValueError("add_to_collection count must be > 0")
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO collection (title, rarity, count)
            VALUES (?, ?, ?)
            ON CONFLICT(title, rarity) DO UPDATE SET count = count + excluded.count
            """,
            (title, rarity, count),
        )


def get_collection() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT title, rarity, count FROM collection WHERE count > 0 ORDER BY rarity, title"
        ).fetchall()
    return [{"title": r["title"], "rarity": r["rarity"], "count": r["count"]} for r in rows]


def get_deck_cards(deck_id: Optional[str] = None) -> list[dict]:
    deck_id = deck_id or get_active_deck_id()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT title, rarity, count
            FROM deck_cards
            WHERE deck_id = ? AND count > 0
            ORDER BY rarity, title
            """,
            (deck_id,),
        ).fetchall()
    return [{"title": r["title"], "rarity": r["rarity"], "count": r["count"]} for r in rows]


def set_deck_count(title: str, rarity: str, count: int, deck_id: Optional[str] = None) -> None:
    deck_id = deck_id or get_active_deck_id()
    with _connect() as conn:
        if count <= 0:
            conn.execute(
                "DELETE FROM deck_cards WHERE deck_id = ? AND title = ? AND rarity = ?",
                (deck_id, title, rarity),
            )
            return
        conn.execute(
            """
            INSERT INTO deck_cards (deck_id, title, rarity, count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(deck_id, title, rarity) DO UPDATE SET count = excluded.count
            """,
            (deck_id, title, rarity, count),
        )


def add_to_deck(title: str, rarity: str, count: int = 1, deck_id: Optional[str] = None) -> None:
    if count <= 0:
        raise ValueError("add_to_deck count must be > 0")
    deck_id = deck_id or get_active_deck_id()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO deck_cards (deck_id, title, rarity, count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(deck_id, title, rarity) DO UPDATE SET count = count + excluded.count
            """,
            (deck_id, title, rarity, count),
        )


def deck_size(deck_id: Optional[str] = None) -> int:
    deck_id = deck_id or get_active_deck_id()
    with _connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(count), 0) AS total FROM deck_cards WHERE deck_id = ?",
            (deck_id,),
        ).fetchone()
    return int(row["total"] if row else 0)
