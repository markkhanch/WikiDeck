"""WikiDeck historical-people generator.

This generator works only with a curated list of historical personalities and
always produces cards with theme ``LIVING``.
"""

from __future__ import annotations

import json as _json
import os
import os as _os
import random
import re
import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Optional, Tuple
from urllib.parse import quote

import requests

try:
    import ollama
except Exception:
    ollama = None

from config import DB_PATH
from core.effects import Effect
from data.card_contract import (
    normalize_nemesis,
    parse_json_block,
    sanitize_ability_text_value,
    validate_card_contract,
)
from data.db import get_cached_card, get_fallback_cached_card, init_db, save_card
from data.historical_people_pool import HISTORICAL_PERSONALITIES
from data.settings_service import get_bool, get_float, get_int, get_str
from data.wikipedia import get_article

WIKI_SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
WIKI_PAGEVIEWS_API = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "en.wikipedia.org/all-access/user/{}/monthly/{}/{}"
)
HEADERS = {"User-Agent": "WikiDeck/2.0 (historical-cards)"}
_OLLAMA_RUNTIME_AVAILABLE: Optional[bool] = None
_OLLAMA_DOWN_NOTIFIED = False
_OLLAMA_CLIENT = None
_OLLAMA_ACTIVE_HOST: Optional[str] = None
_OLLAMA_CHAT_LOCK = threading.Lock()


def _log(message: str) -> None:
    print(message, flush=True)


def _ollama_host_setting() -> str:
    return get_str("ai.ollama_host")


def _ollama_model_setting() -> str:
    return get_str("ai.ollama_model")


def _ollama_max_retries_setting() -> int:
    return max(1, get_int("ai.ollama_max_retries"))


def _request_timeout() -> int:
    return max(1, get_int("ai.request_timeout"))


def _summary_min_chars() -> int:
    return max(1, get_int("ai.summary_min_chars"))


def _summary_max_chars() -> int:
    return max(_summary_min_chars(), get_int("ai.summary_max_chars"))


_GWENT_EXAMPLES = None


def _load_gwent_examples():
    global _GWENT_EXAMPLES
    if _GWENT_EXAMPLES is not None:
        return _GWENT_EXAMPLES
    path = _os.path.join(_os.path.dirname(__file__), "gwent_examples.json")
    try:
        with open(path) as f:
            _GWENT_EXAMPLES = _json.load(f)
    except Exception:
        _GWENT_EXAMPLES = []
    return _GWENT_EXAMPLES

RARITY_WEIGHTS = {"COMMON": 70, "UNCOMMON": 20, "RARE": 8, "EPIC": 2, "LEGENDARY": 0}

RARITY_BUDGETS = {
    "COMMON": 2.0,
    "UNCOMMON": 2.4,
    "RARE": 2.8,
    "EPIC": 3.2,
    "LEGENDARY": 3.8,
}

RARITY_PROVISION = {
    "COMMON": (4, 5),
    "UNCOMMON": (6, 7),
    "RARE": (8, 9),
    "EPIC": (10, 11),
    "LEGENDARY": (12, 14),
}


def _gwent_few_shot(rarity: str, n: int = 4) -> str:
    examples = _load_gwent_examples()
    prov_min, prov_max = RARITY_PROVISION.get(rarity, (4, 5))
    matching = [
        e
        for e in examples
        if prov_min <= e.get("provision", 0) <= prov_max
        and e.get("power", 0) > 0
        and 20 < len(e.get("ability", "")) < 150
    ]
    selected = matching[:n]
    if not selected:
        return ""
    lines = [f"  - {e['ability']}" for e in selected]
    return "\n".join(lines)

HP_CAPS = {"COMMON": 4, "UNCOMMON": 5, "RARE": 6, "EPIC": 7, "LEGENDARY": 8}
MIN_STAT_FLOORS = {"COMMON": 2, "UNCOMMON": 2, "RARE": 3, "EPIC": 3, "LEGENDARY": 4}

ABILITY_COSTS = {
    "DAMAGE": 1.4,
    "DESTROY": 1.8,
    "BANISH": 2.0,
    "HEAL": 1.1,
    "BLEEDING": 1.5,
    "POISON": 1.6,
    "VITALITY": 1.1,
    "SHIELD": 1.2,
    "IMMUNITY": 1.6,
    "LOCK": 1.5,
    "VEIL": 1.4,
    "DOOMED": 1.0,
    "DUEL": 1.8,
    "CLASH": 1.7,
    "DRAW": 1.3,
    "DISCARD": 1.2,
    "REVIVE": 1.7,
}

VALID_EFFECTS = {
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
    "DOOMED",
    "DUEL",
    "CLASH",
    "DRAW",
    "DISCARD",
    "NONE",
}

VALID_TRIGGERS = {
    "DEPLOY",
    "ORDER",
    "ORDER_ZEAL",
    "DEATHWISH",
    "DEATHBLOW",
    "ON DEATH:ally",
    "ON DEATH:enemy",
    "END OF TURN",
    "START OF TURN",
    "TIMER",
    "ADRENALINE",
    "BLOODTHIRST",
    "PASSIVE",
    "NO ABILITY",
}

EFFECT_TYPE_TO_EFFECT = {
    "DAMAGE": Effect.DAMAGE_ENEMY_2,
    "DESTROY": Effect.DAMAGE_ENEMY_2,
    "BANISH": Effect.DAMAGE_ENEMY_2,
    "HEAL": Effect.HEAL_SELF_2,
    "BLEEDING": Effect.NONE,
    "POISON": Effect.NONE,
    "VITALITY": Effect.BUFF_SELF_1,
    "SHIELD": Effect.HEAL_SELF_2,
    "IMMUNITY": Effect.NONE,
    "LOCK": Effect.NONE,
    "VEIL": Effect.NONE,
    "DOOMED": Effect.NONE,
    "DUEL": Effect.DAMAGE_ENEMY_2,
    "CLASH": Effect.DAMAGE_ENEMY_2,
    "DRAW": Effect.DRAW_1,
    "DISCARD": Effect.NONE,
    "REVIVE": Effect.NONE,
    "NONE": Effect.NONE,
}

_KEYWORDS = {
    "war": {
        "war",
        "battle",
        "campaign",
        "siege",
        "army",
        "general",
        "commander",
        "conquer",
        "invasion",
        "military",
        "empire",
    },
    "disease": {
        "disease",
        "plague",
        "epidemic",
        "pandemic",
        "contagion",
        "virus",
        "bacteria",
    },
    "medicine": {
        "medicine",
        "medical",
        "doctor",
        "physician",
        "surgery",
        "hospital",
        "therapy",
        "vaccine",
        "biology",
    },
    "education": {
        "education",
        "teacher",
        "school",
        "academy",
        "philosopher",
        "writer",
        "poet",
        "scientist",
        "theory",
        "research",
        "discovery",
        "inventor",
    },
    "culture": {
        "culture",
        "literature",
        "music",
        "musician",
        "composer",
        "artist",
        "painter",
        "sculptor",
        "poet",
        "novelist",
        "playwright",
    },
    "economy": {
        "economy",
        "economic",
        "trade",
        "market",
        "merchant",
        "finance",
        "coin",
        "tax",
        "bank",
        "diplomat",
        "diplomacy",
    },
    "collapse": {"collapse", "fall", "ruin", "decline", "chaos", "destruction", "genocide"},
    "fortress": {"fortress", "wall", "defense", "defence", "shield", "stronghold", "citadel"},
    "assassin": {"assassin", "murder", "killed", "execution", "terror", "tyrant", "dictator"},
    "politics": {
        "politics",
        "political",
        "state",
        "government",
        "president",
        "king",
        "queen",
        "emperor",
        "prime minister",
        "revolution",
        "leader",
    },
    "religion": {
        "religion",
        "religious",
        "church",
        "pope",
        "saint",
        "missionary",
        "spiritual",
        "faith",
        "monk",
        "theology",
    },
}


def ollama_available() -> bool:
    return bool(get_bool("ai.use_ollama") and ollama is not None)


def _normalize_host(host: str) -> str:
    if not host:
        return "http://127.0.0.1:11434"
    fixed = host.strip().rstrip("/")
    if not fixed.startswith(("http://", "https://")):
        fixed = f"http://{fixed}"
    return fixed


def _host_candidates() -> list[str]:
    candidates = [_normalize_host(_ollama_host_setting()), "http://127.0.0.1:11434", "http://localhost:11434"]
    seen: set[str] = set()
    out: list[str] = []
    for host in candidates:
        if host in seen:
            continue
        seen.add(host)
        out.append(host)
    return out


def _ping_ollama(host: str) -> bool:
    try:
        response = requests.get(f"{host}/api/tags", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def _build_ollama_client(host: str):
    if ollama is None:
        return None
    if hasattr(ollama, "Client"):
        return ollama.Client(host=host, timeout=_request_timeout())
    return None


def _ensure_ollama_runtime() -> bool:
    global _OLLAMA_ACTIVE_HOST, _OLLAMA_CLIENT
    if ollama is None:
        return False

    for host in _host_candidates():
        if _ping_ollama(host):
            _OLLAMA_ACTIVE_HOST = host
            _OLLAMA_CLIENT = _build_ollama_client(host)
            os.environ["OLLAMA_HOST"] = host
            _log(f"[ai] connected to Ollama at {host}")
            return True

    _log(f"[ai] Ollama not reachable. Checked hosts: {', '.join(_host_candidates())}")
    return False


def pick_random_rarity(weights: Optional[dict[str, int]] = None) -> str:
    table = weights or RARITY_WEIGHTS
    names = list(table.keys())
    probs = list(table.values())
    return random.choices(names, weights=probs, k=1)[0]


def _fetch_summary_from_api(title: str) -> Optional[str]:
    safe_title = title.replace(" ", "_")
    url = WIKI_SUMMARY_API.format(safe_title)
    try:
        response = requests.get(url, headers=HEADERS, timeout=_request_timeout())
        if response.status_code != 200:
            return None
        data = response.json()
        if data.get("type") == "disambiguation":
            return None
        extract = (data.get("extract") or "").strip()
        if len(extract) < _summary_min_chars():
            return None
        return extract
    except Exception:
        return None


def _load_historical_pool() -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for title in HISTORICAL_PERSONALITIES:
        norm = title.strip()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        unique.append(norm)
    return unique


ARTICLE_POOL = _load_historical_pool()

_NON_PERSON_TITLE_MARKERS = (
    "(band)",
    "(film)",
    "(album)",
    "(song)",
    "(company)",
    "(organization)",
    "(newspaper)",
    "(novel)",
    "(book)",
    "(tv series)",
)

_NON_PERSON_SUMMARY_PHRASES = (
    " is a band",
    " was a band",
    " is an american rock band",
    " is a city",
    " is a country",
    " is a river",
    " is a mountain",
    " is a lake",
    " is an island",
    " is a film",
    " is a television series",
    " is an organization",
    " is a company",
    " is a newspaper",
    " is a novel",
    " is a book",
    " is an album",
    " is a song",
    " is a genus",
    " is a species",
)

_PERSON_CUES = (
    " leader",
    " ruler",
    " king",
    " queen",
    " emperor",
    " president",
    " prime minister",
    " politician",
    " diplomat",
    " general",
    " commander",
    " military",
    " philosopher",
    " scientist",
    " physicist",
    " chemist",
    " biologist",
    " mathematician",
    " physician",
    " doctor",
    " writer",
    " poet",
    " artist",
    " painter",
    " composer",
    " actor",
    " actress",
    " historian",
    " explorer",
    " religious",
    " theologian",
    " saint",
)


def _looks_like_person(title: str, summary: str) -> bool:
    low_title = title.lower()
    if any(marker in low_title for marker in _NON_PERSON_TITLE_MARKERS):
        return False

    low = summary.lower()
    if any(phrase in low for phrase in _NON_PERSON_SUMMARY_PHRASES):
        return False

    first_sentence = low.split(".", 1)[0]
    if any(cue in first_sentence for cue in _PERSON_CUES):
        return True
    if " born " in low or " died " in low:
        return True
    return False


# In-process cache for pageviews. The pool-walker can ask for the same title
# many times within one session (rejections, retries), and the Wikimedia
# pageviews endpoint rate-limits aggressively. Cache for the lifetime of the
# process — pageviews change monthly, that's fine.
_PAGEVIEWS_CACHE: dict[str, int] = {}


def get_monthly_views(title: str) -> int:
    cached = _PAGEVIEWS_CACHE.get(title)
    if cached is not None:
        return cached

    safe_title = quote(title.replace(" ", "_"), safe="")
    now = datetime.now(UTC)
    first_of_this_month = datetime(now.year, now.month, 1, tzinfo=UTC)
    last_of_prev_month = first_of_this_month - timedelta(days=1)
    first_of_prev_month = datetime(last_of_prev_month.year, last_of_prev_month.month, 1, tzinfo=UTC)
    start = first_of_prev_month.strftime("%Y%m%d00")
    end = last_of_prev_month.strftime("%Y%m%d00")
    url = WIKI_PAGEVIEWS_API.format(safe_title, start, end)

    views: Optional[int] = None
    for attempt in range(4):
        try:
            response = requests.get(url, headers=HEADERS, timeout=_request_timeout())
        except requests.RequestException:
            time.sleep(0.4 * (attempt + 1))
            continue
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            try:
                delay = int(retry_after) if retry_after else 1
            except ValueError:
                delay = 1
            time.sleep(min(5, max(1, delay)) * (attempt + 1))
            continue
        if response.status_code == 404:
            # No data for this article in the requested range — treat as 0,
            # don't retry (Wikimedia returns 404 for unknown titles too).
            views = 0
            break
        if response.status_code >= 500:
            time.sleep(0.6 * (attempt + 1))
            continue
        if response.status_code != 200:
            views = 0
            break
        try:
            items = response.json().get("items") or []
        except ValueError:
            items = []
        views = int(items[-1].get("views", 0) or 0) if items else 0
        break

    if views is None:
        # All attempts exhausted (probably persistent rate-limit) — don't poison
        # the cache so a later call can still recover.
        return 0
    _PAGEVIEWS_CACHE[title] = views
    return views


def assign_rarity_by_views(views: int) -> str:
    """Assign card rarity based on Wikipedia monthly pageviews."""
    if views >= 1_000_000:
        return "LEGENDARY"
    if views >= 300_000:
        return "EPIC"
    if views >= 100_000:
        return "RARE"
    if views >= 30_000:
        return "UNCOMMON"
    return "COMMON"


def _title_exists_in_cards(title: str) -> bool:
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        row = conn.execute("SELECT 1 FROM cards WHERE title = ? LIMIT 1", (title,)).fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False


def _extract_person_article_fields(article: dict | None) -> tuple[str, str] | None:
    if not isinstance(article, dict):
        return None
    article_title = str(article.get("title", "")).strip()
    extract = str(article.get("extract", "")).strip()
    if not article_title or len(extract) < _summary_min_chars():
        return None
    if not _looks_like_person(article_title, extract):
        return None
    return article_title, extract


def get_article_from_pool(
    diversity: Optional[dict] = None,
    pack_rarity: Optional[str] = None,
) -> Tuple[str, str, str]:
    if not ARTICLE_POOL:
        raise RuntimeError("Historical personalities pool is empty.")

    max_attempts = min(120, len(ARTICLE_POOL) * 2)
    for _ in range(max_attempts):
        title = random.choice(ARTICLE_POOL)
        if _title_exists_in_cards(title):
            continue
        summary = _fetch_summary_from_api(title)
        if summary and _looks_like_person(title, summary):
            views = get_monthly_views(title)
            rarity = assign_rarity_by_views(views)
            if pack_rarity is not None:
                _log(f"  -> {title} | views: {views:,}/month | pack rarity: {pack_rarity}")
            else:
                _log(f"  -> Rarity: {rarity} ({views:,} views/month)")
            return title, summary, rarity

    pool_copy = list(ARTICLE_POOL)
    random.shuffle(pool_copy)
    for title in pool_copy:
        if _title_exists_in_cards(title):
            continue
        fallback = get_article(title)
        extracted = _extract_person_article_fields(fallback)
        if extracted is not None:
            fallback_title, fallback_summary = extracted
            views = get_monthly_views(fallback_title)
            rarity = assign_rarity_by_views(views)
            if pack_rarity is not None:
                _log(f"  -> {fallback_title} | views: {views:,}/month | pack rarity: {pack_rarity}")
            else:
                _log(f"  -> Rarity: {rarity} ({views:,} views/month)")
            return fallback_title, fallback_summary, rarity

    # Pool may be exhausted (all titles already in cards). In that case,
    # gracefully allow a repeat instead of hard failing generation.
    for title in pool_copy:
        fallback = get_article(title)
        extracted = _extract_person_article_fields(fallback)
        if extracted is not None:
            fallback_title, fallback_summary = extracted
            views = get_monthly_views(fallback_title)
            rarity = assign_rarity_by_views(views)
            if pack_rarity is not None:
                _log(f"  -> {fallback_title} | views: {views:,}/month | pack rarity: {pack_rarity}")
            else:
                _log(f"  -> Rarity: {rarity} ({views:,} views/month)")
            return fallback_title, fallback_summary, rarity

    raise RuntimeError("No valid historical titles available in pool.")


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


def _signal_hits(title: str, summary: str) -> dict[str, int]:
    tokens = _tokenize(f"{title} {summary}")
    return {
        signal: sum(1 for kw in keywords if kw in tokens or kw in summary.lower())
        for signal, keywords in _KEYWORDS.items()
    }


def _choose_epoch(summary: str) -> str:
    text = summary.lower()
    if any(token in text for token in ("bc", "bce", "ancient", "roman empire")):
        return "ANCIENT"
    if any(token in text for token in ("medieval", "feudal", "caliphate", "crusade")):
        return "MEDIEVAL"
    if any(token in text for token in ("renaissance", "enlightenment", "industrial", "colonial")):
        return "EARLY_MODERN"
    if any(token in text for token in ("world war", "cold war", "modern", "20th", "21st")):
        return "MODERN"
    return "MODERN"


def _effect_candidates(hits: dict[str, int], theme: str = "LIVING") -> list[str]:
    candidates: list[str] = []

    if hits.get("war", 0):
        candidates.extend(["DAMAGE", "DESTROY", "CLASH", "DUEL"])
    if hits.get("medicine", 0) or hits.get("disease", 0):
        candidates.extend(["HEAL", "VITALITY", "BLEEDING", "POISON"])
    if hits.get("assassin", 0) or hits.get("collapse", 0):
        candidates.extend(["BLEEDING", "POISON", "DESTROY"])
    if hits.get("education", 0):
        candidates.extend(["DRAW", "VITALITY"])
    if hits.get("culture", 0):
        candidates.extend(["VITALITY", "SHIELD", "DRAW"])
    if hits.get("religion", 0):
        candidates.extend(["REVIVE", "VITALITY", "HEAL"])
    if hits.get("politics", 0) or hits.get("economy", 0):
        candidates.extend(["LOCK", "BANISH"])
    if hits.get("fortress", 0):
        candidates.extend(["SHIELD", "IMMUNITY", "VEIL"])

    if not candidates:
        if theme == "LIVING":
            candidates = ["DRAW", "VITALITY", "HEAL", "SHIELD"]
        else:
            candidates = ["VITALITY"]

    unique: list[str] = []
    for effect in candidates:
        if effect not in unique:
            unique.append(effect)
    return [effect for effect in unique if effect in VALID_EFFECTS]


ARCHETYPES = ("WARRIOR", "SCHOLAR", "HEALER", "TYRANT", "ARTIST", "DIPLOMAT")


# Archetype -> weighted distribution of which game effects this class prefers.
# Weights are relative; the picker normalizes them. Sum doesn't need to be 100.
ARCHETYPE_EFFECT_WEIGHTS: dict[str, dict[str, int]] = {
    "WARRIOR":  {"DAMAGE": 35, "DESTROY": 20, "CLASH": 15, "DUEL": 15, "BANISH": 10, "BLEEDING": 5},
    "TYRANT":   {"POISON": 25, "BLEEDING": 20, "DOOMED": 15, "DESTROY": 15, "DISCARD": 15, "BANISH": 10},
    "HEALER":   {"HEAL": 30, "VITALITY": 25, "SHIELD": 20, "IMMUNITY": 15, "REVIVE": 10},
    "SCHOLAR":  {"DRAW": 35, "LOCK": 20, "VEIL": 15, "REVIVE": 15, "DISCARD": 15},
    "ARTIST":   {"VITALITY": 25, "DRAW": 20, "SHIELD": 15, "REVIVE": 15, "HEAL": 15, "IMMUNITY": 10},
    "DIPLOMAT": {"LOCK": 30, "DISCARD": 20, "BANISH": 15, "VEIL": 15, "DRAW": 10, "IMMUNITY": 10},
}


# Archetype -> weighted distribution of which triggers fit this class.
# Triggers no longer pull cards into ON-DEATH purely because of effect type.
ARCHETYPE_TRIGGER_WEIGHTS: dict[str, dict[str, int]] = {
    "WARRIOR":  {"DEPLOY": 50, "DEATHBLOW": 20, "BLOODTHIRST": 15, "ADRENALINE": 10, "PASSIVE": 5},
    "TYRANT":   {"DEPLOY": 35, "ON DEATH:enemy": 20, "DEATHBLOW": 20, "ORDER": 15, "TIMER": 10},
    "HEALER":   {"DEPLOY": 35, "ON DEATH:ally": 25, "DEATHWISH": 20, "ORDER": 15, "PASSIVE": 5},
    "SCHOLAR":  {"ORDER": 35, "DEPLOY": 30, "TIMER": 15, "DEATHWISH": 10, "PASSIVE": 10},
    "ARTIST":   {"DEPLOY": 35, "DEATHWISH": 30, "ORDER": 20, "TIMER": 10, "PASSIVE": 5},
    "DIPLOMAT": {"ORDER": 35, "DEPLOY": 30, "DEATHBLOW": 15, "TIMER": 10, "PASSIVE": 10},
}


# Target global shares of effects across the whole DB. Used to bias the
# weighted picker toward effects that are underrepresented overall. Sums to 1.
EFFECT_TARGET_SHARE: dict[str, float] = {
    "DAMAGE":   0.18,
    "DESTROY":  0.08,
    "BANISH":   0.06,
    "BLEEDING": 0.07,
    "POISON":   0.05,
    "DUEL":     0.05,
    "CLASH":    0.05,
    "HEAL":     0.07,
    "VITALITY": 0.08,
    "SHIELD":   0.06,
    "IMMUNITY": 0.04,
    "DRAW":     0.08,
    "DISCARD":  0.04,
    "LOCK":     0.05,
    "VEIL":     0.03,
    "REVIVE":   0.02,
    "DOOMED":   0.02,
}

TRIGGER_TARGET_SHARE: dict[str, float] = {
    "DEPLOY":          0.35,
    "ORDER":           0.20,
    "DEATHWISH":       0.10,
    "DEATHBLOW":       0.10,
    "ON DEATH:ally":   0.05,
    "ON DEATH:enemy":  0.04,
    "TIMER":           0.06,
    "ADRENALINE":      0.04,
    "BLOODTHIRST":     0.04,
    "PASSIVE":         0.04,
}


_GLOBAL_DIST_CACHE: dict[str, tuple[float, dict[str, int]]] = {}
_GLOBAL_DIST_TTL_SEC = 30.0


def _global_effect_distribution() -> dict[str, int]:
    """Cached snapshot of the current effect distribution in the DB."""
    from data.db import get_effect_distribution
    now = time.time()
    cached = _GLOBAL_DIST_CACHE.get("effects")
    if cached and now - cached[0] < _GLOBAL_DIST_TTL_SEC:
        return cached[1]
    try:
        snap = get_effect_distribution()
    except Exception:
        snap = {}
    _GLOBAL_DIST_CACHE["effects"] = (now, snap)
    return snap


def _global_trigger_distribution() -> dict[str, int]:
    from data.db import get_trigger_distribution
    now = time.time()
    cached = _GLOBAL_DIST_CACHE.get("triggers")
    if cached and now - cached[0] < _GLOBAL_DIST_TTL_SEC:
        return cached[1]
    try:
        snap = get_trigger_distribution()
    except Exception:
        snap = {}
    _GLOBAL_DIST_CACHE["triggers"] = (now, snap)
    return snap


def invalidate_distribution_cache() -> None:
    """Call when many new cards are written and the snapshot is stale."""
    _GLOBAL_DIST_CACHE.clear()


def _global_adjustment(
    key: str,
    distribution: dict[str, int],
    targets: dict[str, float],
) -> float:
    """Multiplier for `key`'s weight based on how its global share compares to target."""
    total = sum(distribution.values())
    if total < 30:
        # Too little data — don't try to balance yet, let archetype weights drive.
        return 1.0
    target = targets.get(key, 0.0)
    if target <= 0:
        return 1.0
    actual = distribution.get(key, 0) / total
    ratio = actual / target
    if ratio >= 1.5:
        return 0.2
    if ratio >= 1.0:
        return 0.6
    if ratio <= 0.5:
        return 1.8
    return 1.0


# Pairs that don't make sense to combine — skip during trigger selection.
# e.g. ADRENALINE (boost-when-near-death) doesn't fit defensive heals.
INCOMPATIBLE_TRIGGER_EFFECT: set[tuple[str, str]] = {
    ("ADRENALINE", "HEAL"), ("ADRENALINE", "VITALITY"),
    ("ADRENALINE", "SHIELD"), ("ADRENALINE", "IMMUNITY"),
    ("BLOODTHIRST", "HEAL"), ("BLOODTHIRST", "SHIELD"),
    ("ON DEATH:enemy", "HEAL"), ("ON DEATH:enemy", "VITALITY"),
    ("ON DEATH:enemy", "SHIELD"), ("ON DEATH:enemy", "IMMUNITY"),
    ("ON DEATH:enemy", "REVIVE"),
    ("ON DEATH:ally", "DAMAGE"), ("ON DEATH:ally", "DESTROY"),
    ("ON DEATH:ally", "BANISH"), ("ON DEATH:ally", "POISON"),
    ("ON DEATH:ally", "BLEEDING"),
    ("DEATHBLOW", "HEAL"), ("DEATHBLOW", "REVIVE"),
    ("DEATHWISH", "DAMAGE"), ("DEATHWISH", "DESTROY"), ("DEATHWISH", "BANISH"),
    ("PASSIVE", "DESTROY"), ("PASSIVE", "BANISH"),
}


def _weighted_pick(
    weights: dict[str, int],
    bucket: dict[str, int],
    total_in_pack: int,
    max_share: float,
    forbidden: set[str] | None = None,
    global_distribution: dict[str, int] | None = None,
    target_shares: dict[str, float] | None = None,
) -> str:
    """Pick from a weighted distribution, biased away from over-saturated items.

    Two layers of bias:
      - per-pack: each pack of 5 should not exceed `max_share` of one key.
      - global:  the whole DB drifts toward `target_shares` proportions.
    """
    forbidden = forbidden or set()
    pool = {k: w for k, w in weights.items() if k not in forbidden and w > 0}
    if not pool:
        # All forbidden — relax constraint.
        pool = {k: w for k, w in weights.items() if w > 0}
    if not pool:
        return next(iter(weights))

    adjusted: dict[str, float] = {}
    denom = max(1, total_in_pack)
    for key, base in pool.items():
        weight = float(base)

        # Per-pack penalty.
        share = bucket.get(key, 0) / denom
        if share >= max_share:
            weight *= 0.1
        elif share >= max_share * 0.6:
            weight *= 0.5

        # Global DB-wide adjustment toward target shares.
        if global_distribution is not None and target_shares is not None:
            weight *= _global_adjustment(key, global_distribution, target_shares)

        adjusted[key] = weight

    keys = list(adjusted.keys())
    vals = list(adjusted.values())
    return random.choices(keys, weights=vals, k=1)[0]


def _choose_archetype(hits: dict[str, int], effect_type: str) -> str:
    """Pick a thematic archetype from Wikipedia keyword signals.

    Falls back to mapping the chosen effect_type to a class when the article
    has no strong biographical cues.
    """
    war = hits.get("war", 0)
    assassin = hits.get("assassin", 0) + hits.get("collapse", 0)
    medicine = hits.get("medicine", 0) + hits.get("disease", 0)
    religion = hits.get("religion", 0)
    education = hits.get("education", 0)
    culture = hits.get("culture", 0)
    politics = hits.get("politics", 0) + hits.get("economy", 0)

    scores = {
        "WARRIOR": war + hits.get("fortress", 0),
        "TYRANT": assassin,
        "HEALER": medicine + religion,
        "SCHOLAR": education,
        "ARTIST": culture,
        "DIPLOMAT": politics,
    }
    top = max(scores.values())
    if top > 0:
        # Prefer archetype with strongest signal; ties broken by declared order.
        for arch in ("WARRIOR", "TYRANT", "HEALER", "SCHOLAR", "ARTIST", "DIPLOMAT"):
            if scores[arch] == top:
                return arch

    # Fallback: derive from effect_type.
    effect_to_arch = {
        "DAMAGE": "WARRIOR", "DESTROY": "WARRIOR", "CLASH": "WARRIOR", "DUEL": "WARRIOR",
        "BANISH": "TYRANT", "BLEEDING": "TYRANT", "POISON": "TYRANT", "DOOMED": "TYRANT",
        "HEAL": "HEALER", "VITALITY": "HEALER", "SHIELD": "HEALER", "IMMUNITY": "HEALER",
        "DRAW": "SCHOLAR", "VEIL": "SCHOLAR", "REVIVE": "SCHOLAR",
        "LOCK": "DIPLOMAT", "DISCARD": "DIPLOMAT",
    }
    return effect_to_arch.get(effect_type, "SCHOLAR")


def _trigger_candidates(effect_type: str) -> list[str]:
    if effect_type in {"DAMAGE", "DESTROY", "BANISH", "BLEEDING", "POISON", "LOCK", "DUEL", "CLASH"}:
        return ["DEPLOY", "DEATHBLOW"]
    if effect_type in {"HEAL", "VITALITY", "SHIELD", "IMMUNITY", "VEIL", "REVIVE"}:
        return ["DEPLOY", "DEATHWISH", "ON DEATH:ally"]
    if effect_type in {"DRAW", "DISCARD"}:
        return ["DEPLOY", "ORDER", "DEATHBLOW"]
    return ["DEPLOY"]


def _choose_with_diversity(
    candidates: list[str],
    bucket: dict[str, int],
    total: int,
    max_share: float,
) -> str:
    if len(candidates) == 1:
        return candidates[0]

    random.shuffle(candidates)
    for candidate in candidates:
        if total <= 0:
            return candidate
        if (bucket.get(candidate, 0) + 1) / max(total, 1) <= max_share:
            return candidate
    return min(candidates, key=lambda value: bucket.get(value, 0))


def _ability_value(effect_type: str, rarity: str) -> int:
    # Numbered effects: scale value by rarity.
    if effect_type in {"DAMAGE", "BLEEDING", "VITALITY", "DRAW", "DISCARD"}:
        return 1 if rarity == "COMMON" else 2
    # Everything else is numberless (POISON, DESTROY, BANISH, HEAL, ...).
    return 0


def _ability_text_template(effect_type: str, value: int) -> str:
    if effect_type == "DAMAGE":
        return f"Deal {value} damage to one enemy card."
    if effect_type == "DESTROY":
        return "Destroy one enemy card."
    if effect_type == "BANISH":
        return "Banish one enemy card."
    if effect_type == "HEAL":
        return "Heal this card."
    if effect_type == "BLEEDING":
        return f"Give an enemy card Bleeding for {value} turns."
    if effect_type == "POISON":
        return "Give an enemy card Poison."
    if effect_type == "VITALITY":
        return f"Give this card Vitality for {value} turns."
    if effect_type == "SHIELD":
        return "Give this card Shield."
    if effect_type == "IMMUNITY":
        return "Give this card Immunity."
    if effect_type == "LOCK":
        return "Lock an enemy card."
    if effect_type == "VEIL":
        return "Give this card Veil."
    if effect_type == "DUEL":
        return "Duel an enemy card."
    if effect_type == "CLASH":
        return "Clash with one enemy card."
    if effect_type == "DRAW":
        return f"Draw {value} cards."
    if effect_type == "DISCARD":
        return f"Discard {value} cards from the enemy hand."
    if effect_type == "REVIVE":
        return "Return one card from your discard pile to the field."
    return "Give this card Vitality for 1 turn."


def _with_trigger_context(trigger: str, ability_text: str) -> str:
    stripped = ability_text.strip()
    if trigger == "ORDER":
        return f"Order: {stripped}"
    if trigger == "ORDER_ZEAL":
        return f"Order: {stripped}"
    if trigger == "DEATHWISH":
        return f"Deathwish: {stripped}"
    if trigger == "DEATHBLOW":
        return f"Deathblow: {stripped}"
    if trigger == "TIMER":
        return f"Timer 2: {stripped}"
    return stripped


def build_grounded_spec(
    title: str,
    summary: str,
    rarity: str,
    diversity: Optional[dict] = None,
    avoid_effects: Optional[set[str]] = None,
) -> dict:
    diversity = diversity or {}
    avoid_effects = avoid_effects or set()
    hits = _signal_hits(title, summary)

    effect_bucket = diversity.get("effects", {})
    trigger_bucket = diversity.get("triggers", {})
    total = max(int(diversity.get("target", 1)), 1)

    # 1) Pick archetype from Wikipedia signals first (or random if no signals).
    archetype = _choose_archetype(hits, effect_type="")
    if archetype not in ARCHETYPE_EFFECT_WEIGHTS:
        archetype = random.choice(ARCHETYPES)

    # 2) Effect is picked from the archetype's weighted distribution, biased
    #    away from effects already saturated in this pack AND globally in DB.
    global_effects = _global_effect_distribution()
    effect_type = _weighted_pick(
        ARCHETYPE_EFFECT_WEIGHTS[archetype],
        effect_bucket,
        total,
        max_share=0.35,
        forbidden=avoid_effects,
        global_distribution=global_effects,
        target_shares=EFFECT_TARGET_SHARE,
    )

    # 3) Trigger is also from the archetype distribution, filtered to be
    #    compatible with the chosen effect, biased globally toward target.
    trigger_weights = dict(ARCHETYPE_TRIGGER_WEIGHTS[archetype])
    for trig in list(trigger_weights.keys()):
        if (trig, effect_type) in INCOMPATIBLE_TRIGGER_EFFECT:
            trigger_weights.pop(trig, None)
    if not trigger_weights:
        trigger_weights = {"DEPLOY": 1}
    global_triggers = _global_trigger_distribution()
    trigger = _weighted_pick(
        trigger_weights,
        trigger_bucket,
        total,
        max_share=0.55,
        global_distribution=global_triggers,
        target_shares=TRIGGER_TARGET_SHARE,
    )

    value = _ability_value(effect_type, rarity)

    return {
        "title": title,
        "theme": "LIVING",
        "epoch": _choose_epoch(summary),
        "rarity": rarity,
        "trigger": trigger,
        "trigger_value": 0,
        "effect_type": effect_type,
        "ability_value": value,
        "ability_text": _with_trigger_context(trigger, _ability_text_template(effect_type, value)),
        "nemesis": None,
        "archetype": archetype,
        "source_type": "WIKIPEDIA",
        "source_ref": title,
        "summary_snippet": summary[:_summary_max_chars()],
    }


def build_system_prompt() -> str:
    return (
        "You are writing card text for WikiDeck — a trading card game whose\n"
        "cards are real historical personalities. For each card, the engine\n"
        "has already chosen the mechanic, the trigger, the numeric value,\n"
        "and the archetype (class). You write two things:\n"
        "  1) ability_text  — short, strict mechanical sentence (game text)\n"
        "  2) rationale     — one biographical sentence connecting the person\n"
        "                     to the mechanic (flavor text shown on hover)\n\n"
        "Rules for ability_text:\n"
        "- Under 20 words\n"
        "- Must contain ONLY mechanic and target (no explanations, no flavor)\n"
        "- One verb, one target, period\n"
        "- Only use these game terms: HP, BLEEDING, VITALITY, POISON,\n"
        "  SHIELD, IMMUNITY, LOCK, VEIL, cards\n"
        "FORBIDDEN words - never use these in ability_text:\n"
        "attack, defense, morale, faith, influence, power, strength, mana\n"
        "- If trigger is DEATHWISH, ability_text MUST start with: \"Deathwish: ...\"\n"
        "- If trigger is DEATHBLOW, ability_text MUST start with: \"Deathblow: ...\"\n"
        "- If trigger is ORDER or ORDER_ZEAL, ability_text MUST start with: \"Order: ...\"\n"
        "- Never write card names in ability_text (forbidden: 'When Frida Kahlo dies, ...')\n"
        "- For all other triggers, do not include trigger words in ability_text\n"
        "- One effect only - never combine two effects in one sentence\n"
        "- Complete sentence with a period\n\n"
        "DEPLOY examples:\n"
        '- "Deal 2 damage to one enemy card."\n'
        '- "Give this card Vitality for 2 turns."\n'
        '- "Give an enemy card Bleeding for 3 turns."\n'
        '- "Give this card Immunity."\n'
        '- "Give this card Shield."\n'
        '- "Lock an enemy card."\n'
        '- "Destroy one enemy card."\n'
        '- "Banish one enemy card."\n'
        '- "Give an enemy card Poison."\n'
        '- "Duel an enemy card."\n'
        '- "Draw 1 card."\n'
        '- "Gain 2 gold."\n\n'
        "ORDER examples (can be used once per turn):\n"
        '- "Order: Deal 3 damage to one enemy card."\n'
        '- "Order: Give this card Vitality for 2 turns."\n'
        '- "Order: Heal this card."\n\n'
        "DEATHWISH examples (trigger on this card's death):\n"
        '- "Deathwish: Give this card Vitality for 2 turns."\n'
        '- "Deathwish: Draw 2 cards."\n'
        '- "Deathwish: Deal 2 damage to all enemy cards."\n\n'
        "DEATHBLOW examples (trigger when this card destroys another):\n"
        '- "Deathblow: Gain 2 gold."\n'
        '- "Deathblow: Give this card Vitality for 3 turns."\n'
        '- "Deathblow: Draw 1 card."\n\n'
        "TIMER examples:\n"
        '- "Timer 3: Destroy the highest-HP enemy card."\n'
        '- "Timer 2: Give this card Vitality for 4 turns."\n\n'
        "BLEEDING examples:\n"
        '- "Give an enemy card Bleeding for 2 turns."\n\n'
        "WRONG:\n"
        '- "Deal 2 damage and draw 1 card."\n'
        '- "Order Give this card Vitality for 2 turns."\n'
        '- "When deployed, deal 2 damage."\n\n'
        "Rules for nemesis:\n"
        "- A real Wikipedia article title of a historical rival or opponent\n"
        "- Must be someone this person actually opposed in real history\n"
        "- Write null if no clear historical nemesis exists\n\n"
        "Rules for rationale (this is FLAVOR text — different from ability_text):\n"
        "- One short sentence, 8-18 words, written in present tense.\n"
        "- Ties this person's REAL life or work to the mechanic they perform.\n"
        "- Sounds like a quote or epitaph, not a game rule.\n"
        "- DO NOT mention game terms (damage, vitality, draw, HP, etc).\n"
        "- DO NOT mention the card's own name.\n"
        "- DO NOT explain mechanics — evoke the historical action instead.\n"
        "- End with a period.\n\n"
        "Good rationale examples:\n"
        "- (Confucius, archetype SCHOLAR, draw): \"His teachings outlasted the empires that ignored them.\"\n"
        "- (Napoleon, WARRIOR, damage): \"Artillery announced his arrival before diplomats could speak.\"\n"
        "- (Marie Curie, SCHOLAR, poison): \"She held the glow that killed her, and called it discovery.\"\n"
        "- (Mahatma Gandhi, DIPLOMAT, lock): \"He stopped an empire with silence and a spinning wheel.\"\n"
        "- (Mozart, ARTIST, vitality): \"His melodies still teach the dying how to live.\"\n"
        "- (Genghis Khan, TYRANT, destroy): \"He inherited a tent and left behind a continent of ash.\"\n\n"
        "Bad rationale examples (don't do this):\n"
        "- \"This card deals damage because Napoleon was a warrior.\"  (explains mechanic)\n"
        "- \"Damage fits him.\"  (no biography)\n"
        "- \"Napoleon damages enemies.\"  (uses card name + game term)\n\n"
        "Return ONLY this JSON:\n"
        "{\n"
        '  "title": "EXACT Person value from the user prompt",\n'
        '  "rationale": "one biographical sentence connecting the person to the mechanic",\n'
        '  "ability_text": "...",\n'
        '  "nemesis": null\n'
        "}"
    )


def build_user_prompt(spec: dict, summary: str, avoid_effects: Optional[set[str]] = None) -> str:
    rarity = str(spec.get("rarity", "COMMON")).upper()
    few_shot = _gwent_few_shot(rarity)
    few_shot_block = ""
    if few_shot:
        few_shot_block = f"""
Ability complexity reference for {rarity} cards (from a balanced card game):
{few_shot}
Use these as inspiration for complexity level only - do NOT copy them literally.
Write ability_text using only WikiDeck terms: HP, BLEEDING, VITALITY,
POISON, SHIELD, IMMUNITY, LOCK, VEIL, cards.
"""

    avoid = set(avoid_effects or ())
    avoid_block = ""
    if avoid:
        avoid_block = f"\nFORBIDDEN effects (do NOT pick these): {sorted(avoid)}\n"

    return f"""Person: {spec['title']}
Required title echo: {spec['title']}
Summary: {summary[:_summary_max_chars()]}
Epoch: {spec['epoch']}
Archetype: {spec.get('archetype', 'SCHOLAR')}
Mechanic: {spec['trigger']} -> {spec['effect_type']}
REQUIRED effect in ability_text: {spec['effect_type']}
Ability value: {spec['ability_value']}{avoid_block}

Examples of correct ability_text for different mechanics:
DAMAGE: "Deal 2 damage to one enemy card."
VITALITY: "Give this card Vitality for 2 turns."
BLEEDING: "Give an enemy card Bleeding for 3 turns."
HEAL: "Heal this card."
DRAW: "Draw 2 cards."
DESTROY: "Destroy one enemy card."
BANISH: "Banish one enemy card."
SHIELD: "Give this card Shield."
LOCK: "Lock an enemy card."
REVIVE: "Return one card from your discard pile to the field."
DEATHWISH context: "Deathwish: Give this card Vitality for 1 turn."
{few_shot_block}"""


def _parse_flavor_response(raw_text: str) -> dict:
    payload = parse_json_block(raw_text)
    if "card" in payload and isinstance(payload["card"], dict):
        payload = payload["card"]
    return {
        "title": str(payload.get("title", "")).strip(),
        "rationale": str(payload.get("rationale", "")).strip(),
        "ability_text": str(payload.get("ability_text", "")).strip(),
        "nemesis": normalize_nemesis(payload.get("nemesis")),
    }


def parse_card_response(raw_text: str) -> dict:
    return _parse_flavor_response(raw_text)


def _validate_spec(spec: dict) -> tuple[bool, list[str]]:
    contract = {
        "theme": spec.get("theme"),
        "epoch": spec.get("epoch"),
        "trigger": spec.get("trigger"),
        "trigger_value": 0,
        "effect_type": spec.get("effect_type"),
        "ability_text": spec.get("ability_text"),
        "ability_value": spec.get("ability_value", 0),
        "nemesis": spec.get("nemesis"),
    }
    try:
        validate_card_contract(contract, strict_gameplay=False)
        spec["ability_value"] = int(contract["ability_value"])
        spec["nemesis"] = contract["nemesis"]
        text = str(spec.get("ability_text", "")).strip()
        low = text.lower()
        title_low = str(spec.get("title", "")).strip().lower()
        trigger = str(spec.get("trigger", "")).strip()

        if title_low and title_low in low:
            raise ValueError("ability_text must not contain card name")
        if trigger == "DEATHWISH" and not low.startswith("deathwish:"):
            raise ValueError("DEATHWISH ability_text must start with 'Deathwish:'")
        if trigger == "DEATHBLOW" and not low.startswith("deathblow:"):
            raise ValueError("DEATHBLOW ability_text must start with 'Deathblow:'")
        if trigger in {"ORDER", "ORDER_ZEAL"} and not low.startswith("order:"):
            raise ValueError("ORDER/ORDER_ZEAL ability_text must start with 'Order:'")
        return True, []
    except Exception as exc:
        return False, [str(exc)]


def _generate_flavor(spec: dict, summary: str, retries: int = 4, avoid_effects: Optional[set[str]] = None) -> dict:
    global _OLLAMA_RUNTIME_AVAILABLE, _OLLAMA_DOWN_NOTIFIED
    fallback = {
        "title": spec["title"],
        "rationale": f"{spec['title']} is represented by {spec['effect_type']} based on known historical impact.",
        "ability_text": spec["ability_text"],
        "nemesis": None,
    }
    if not get_bool("ai.use_ollama"):
        return fallback
    if ollama is None:
        print(f"[ai] ollama unavailable, fallback used for {spec['title']}", flush=True)
        return fallback
    with _OLLAMA_CHAT_LOCK:
        if not _ensure_ollama_runtime():
            _OLLAMA_RUNTIME_AVAILABLE = False
            if not _OLLAMA_DOWN_NOTIFIED:
                print("[ai] ollama runtime unavailable, using fallback mode.", flush=True)
                _OLLAMA_DOWN_NOTIFIED = True
            return fallback

    previous_errors: list[str] = []
    base_temp = get_float("ai.temperature")
    for attempt in range(1, retries + 1):
        user_prompt = build_user_prompt(spec, summary, avoid_effects=avoid_effects)
        if previous_errors:
            error_lines = "\n".join(f"- {item}" for item in previous_errors[-3:])
            user_prompt += f"\n\nPrevious issues to fix:\n{error_lines}"
        # Ramp temperature on each retry so the model breaks out of repeated
        # near-identical responses. +0.12 per retry, capped at 1.2.
        attempt_temp = min(1.2, base_temp + 0.12 * (attempt - 1))
        try:
            chat_payload = {
                "model": _ollama_model_setting(),
                "format": "json",
                "options": {"temperature": attempt_temp},
                "messages": [
                    {"role": "system", "content": build_system_prompt()},
                    {"role": "user", "content": user_prompt},
                ],
            }
            with _OLLAMA_CHAT_LOCK:
                if _OLLAMA_CLIENT is not None:
                    response = _OLLAMA_CLIENT.chat(**chat_payload)
                else:
                    response = ollama.chat(**chat_payload)
            content = response["message"]["content"]
            print(f"[ai] response {attempt}/{retries} for {spec['title']}: {content}", flush=True)
            parsed = parse_card_response(content)
            _OLLAMA_RUNTIME_AVAILABLE = True
            _OLLAMA_DOWN_NOTIFIED = False
            print(
                f"[ai] parsed {spec['title']}: ability='{parsed['ability_text']}' nemesis={parsed['nemesis']}",
                flush=True,
            )
            if not parsed["ability_text"]:
                previous_errors.append("ability_text is empty.")
                print(f"[ai] invalid response for {spec['title']}: ability_text is empty", flush=True)
                continue
            if parsed.get("title", "") != spec["title"]:
                previous_errors.append(
                    f"title mismatch: expected '{spec['title']}', got '{parsed.get('title', '')}'"
                )
                print(
                    f"[ai] invalid response for {spec['title']}: title mismatch -> {parsed.get('title', '')}",
                    flush=True,
                )
                continue

            # Sanitize the LLM text (word-numbers → digits, value-injection)
            # BEFORE validating so cosmetic-only issues like "two cards" don't
            # waste retries.
            cleaned_text = sanitize_ability_text_value(
                parsed["ability_text"], int(spec["ability_value"])
            )
            candidate = dict(spec)
            candidate["ability_text"] = cleaned_text
            candidate["nemesis"] = parsed["nemesis"]
            valid, errors = _validate_spec(candidate)
            if valid:
                # Propagate cleaned text back so callers don't re-sanitize.
                parsed["ability_text"] = cleaned_text
                return parsed
            previous_errors.extend(errors)
            print(f"[ai] invalid response for {spec['title']}: {errors}", flush=True)
        except Exception as exc:
            msg = str(exc)
            if "Failed to connect to Ollama" in msg or "Connection refused" in msg:
                reconnected = False
                retries = _ollama_max_retries_setting()
                for reconnect_try in range(retries):
                    with _OLLAMA_CHAT_LOCK:
                        ok = _ensure_ollama_runtime()
                    if ok:
                        reconnected = True
                        _OLLAMA_RUNTIME_AVAILABLE = True
                        _OLLAMA_DOWN_NOTIFIED = False
                        print(f"[ai] reconnect success ({reconnect_try + 1}/{retries})", flush=True)
                        break
                    time.sleep(0.4)
                if reconnected:
                    previous_errors.append("Ollama connection dropped; retrying with reconnected runtime.")
                    continue
                _OLLAMA_RUNTIME_AVAILABLE = False
                if not _OLLAMA_DOWN_NOTIFIED:
                    print(f"[ai] ollama runtime unavailable: {msg}", flush=True)
                    _OLLAMA_DOWN_NOTIFIED = True
                return fallback
            previous_errors.append(f"Ollama failure: {msg}")
            print(f"[ai] error for {spec['title']}: {msg}", flush=True)

    print(f"[ai] retries exhausted, fallback used for {spec['title']}", flush=True)
    return fallback


_RATIONALE_MECHANIC_WORDS = re.compile(
    r"\b(damage|heal|hp|vitality|bleeding|poison|shield|immunity|lock|veil|"
    r"doomed|duel|clash|draw|discard|revive|deploy|order|deathwish|deathblow|"
    r"timer|enemy card|allied card)\b",
    re.IGNORECASE,
)


def _sanitize_rationale(raw: str, title: str) -> str:
    """Trim, strip mechanic leaks, and reject if too short or has the card name."""
    text = " ".join(str(raw or "").split()).strip().strip('"“”').strip()
    if not text:
        return ""
    # If model wrote the card name into the flavor — too on-the-nose, drop it.
    name_low = title.strip().lower()
    if name_low and name_low in text.lower():
        return ""
    # If the model leaked mechanical vocab into flavor — keep the sentence
    # only if it's still readable without those words. Otherwise drop it,
    # the engine will leave the flavor field empty.
    if _RATIONALE_MECHANIC_WORDS.search(text):
        return ""
    # Cap word count.
    words = text.split()
    if len(words) > 22:
        text = " ".join(words[:22]).rstrip(",.;:") + "."
    if not text.endswith((".", "!", "?")):
        text += "."
    return text


def _balance_card(spec: dict) -> dict:
    rarity = spec["rarity"]
    budget = RARITY_BUDGETS.get(rarity, 2.0)
    floor = MIN_STAT_FLOORS.get(rarity, 1)

    effect_type = spec["effect_type"]
    value = int(spec.get("ability_value", 0) or 0)
    cost = ABILITY_COSTS.get(effect_type, 1.0)

    trigger = spec.get("trigger", "DEPLOY")
    if trigger in {"DEATHWISH", "DEATHBLOW", "ON DEATH:ally", "ON DEATH:enemy"}:
        cost += 0.2
    elif trigger in {"PASSIVE", "ORDER", "ORDER_ZEAL"}:
        cost += 0.3

    hp = max(floor, min(HP_CAPS.get(rarity, 5), round(1.2 + budget - 0.6 * cost)))
    spec["hp"] = int(hp)
    return spec


def diversity_allows(diversity: Optional[dict], spec: dict) -> bool:
    if not diversity:
        return True
    target = max(int(diversity.get("target", 1)), 1)
    max_share_effect = float(diversity.get("max_share_effect", 0.35))
    max_share_trigger = float(diversity.get("max_share_trigger", 0.75))
    effect = spec.get("effect_type", "")
    trigger = spec.get("trigger", "")
    effects = diversity.get("effects", {})
    triggers = diversity.get("triggers", {})
    if (effects.get(effect, 0) + 1) / target > max_share_effect:
        return False
    if (triggers.get(trigger, 0) + 1) / target > max_share_trigger:
        return False
    return True


def apply_diversity(diversity: Optional[dict], spec: dict) -> None:
    if not diversity:
        return
    effect = spec.get("effect_type", "")
    trigger = spec.get("trigger", "")
    effects = diversity.setdefault("effects", {})
    triggers = diversity.setdefault("triggers", {})
    effects[effect] = effects.get(effect, 0) + 1
    triggers[trigger] = triggers.get(trigger, 0) + 1


def generate_card_spec(
    title: str,
    summary: str,
    rarity: str,
    diversity: Optional[dict] = None,
) -> dict:
    init_db()
    cached = get_cached_card(title, rarity)
    if cached is not None and cached.get("theme") == "LIVING":
        print(f"[gen] cache hit: {title} [{rarity}]", flush=True)
        return cached

    runtime_available = False
    if ollama is not None:
        with _OLLAMA_CHAT_LOCK:
            runtime_available = _ensure_ollama_runtime()
    if not runtime_available:
        fallback = get_fallback_cached_card(title, rarity)
        if fallback is not None and fallback.get("theme") == "LIVING":
            fallback = dict(fallback)
            fallback["rarity"] = rarity
            fallback["title"] = str(fallback.get("title", title) or title)
            fallback = _balance_card(fallback)
            print(
                f"[gen] db fallback: requested {title} [{rarity}] -> "
                f"{fallback['title']} [{fallback['rarity']}]",
                flush=True,
            )
            return fallback

    print(f"[gen] generating: {title} [{rarity}]", flush=True)
    avoid_effects: set[str] = set()
    for attempt in range(1, 7):
        spec = build_grounded_spec(
            title,
            summary,
            rarity,
            diversity,
            avoid_effects=avoid_effects,
        )
        # Surface avoid list to the LLM prompt so retries differ visibly.
        flavor = _generate_flavor(spec, summary, avoid_effects=avoid_effects)
        spec["rationale"] = _sanitize_rationale(flavor.get("rationale", ""), spec["title"])
        spec["ability_text"] = sanitize_ability_text_value(flavor["ability_text"], int(spec["ability_value"]))
        spec["nemesis"] = flavor["nemesis"]

        valid, errors = _validate_spec(spec)
        if not valid:
            if attempt < 6:
                print(f"[gen] retry {attempt}/6 invalid: {title} -> {errors[0]}", flush=True)
                continue
            # Last attempt: rebuild ability_text from template so the engine
            # gets correct mechanical text. We keep rationale (flavor) intact.
            spec["ability_text"] = _with_trigger_context(
                spec["trigger"],
                _ability_text_template(spec["effect_type"], int(spec["ability_value"])),
            )
            valid, errors = _validate_spec(spec)
            if not valid:
                raise ValueError(f"Invalid card contract for {title} after template fallback: {errors}")
            print(f"[gen] template fallback used for {title} (LLM text was invalid).", flush=True)

        if not diversity_allows(diversity, spec):
            if attempt < 6:
                avoid_effect = str(spec.get("effect_type", "")).strip()
                if avoid_effect:
                    avoid_effects.add(avoid_effect)
                print(f"[gen] retry {attempt}/6 diversity: {title}", flush=True)
                continue

        _balance_card(spec)
        save_card(spec)
        print(
            f"[gen] done: {title} [{rarity}] {spec['trigger']} -> {spec['effect_type']} "
            f"HP={spec['hp']}",
            flush=True,
        )
        return spec

    raise RuntimeError(f"Unable to generate valid card for '{title}'.")


def generate_card_response(title: str, summary: str, rarity: str) -> str:
    spec = generate_card_spec(title, summary, rarity)
    return (
        "{\n"
        '  "rationale": "%s",\n'
        '  "card": {\n'
        '    "title": "%s",\n'
        '    "theme": "%s",\n'
        '    "epoch": "%s",\n'
        '    "rarity": "%s",\n'
        '    "trigger": "%s",\n'
        '    "trigger_value": %d,\n'
        '    "effect_type": "%s",\n'
        '    "ability_value": %d,\n'
        '    "ability_text": "%s",\n'
        '    "nemesis": %s,\n'
        '    "hp": %d,\n'
        '    "source_type": "%s",\n'
        '    "source_ref": "%s",\n'
        '    "summary_snippet": "%s"\n'
        "  }\n"
        "}"
        % (
            spec.get("rationale", "").replace('"', '\\"'),
            spec["title"].replace('"', '\\"'),
            spec["theme"],
            spec["epoch"],
            spec["rarity"],
            spec["trigger"],
            int(spec.get("trigger_value", 0)),
            spec["effect_type"],
            int(spec["ability_value"]),
            spec["ability_text"].replace('"', '\\"'),
            "null" if spec.get("nemesis") is None else f"\"{spec['nemesis'].replace('\"', '\\\"')}\"",
            int(spec["hp"]),
            spec["source_type"],
            spec["source_ref"].replace('"', '\\"'),
            spec["summary_snippet"].replace('"', '\\"'),
        )
    )


def generate_card_specs(count: int = 10, rarity: Optional[str] = None) -> list[dict]:
    cards: list[dict] = []
    seen: set[str] = set()
    diversity = {"effects": {}, "triggers": {}, "target": max(count, 1)}

    attempts = 0
    max_attempts = count * 20
    while len(cards) < count and attempts < max_attempts:
        attempts += 1
        title, summary, sourced_rarity = get_article_from_pool(diversity=diversity)
        if title in seen:
            continue
        this_rarity = rarity or sourced_rarity
        spec = generate_card_spec(title, summary, this_rarity, diversity=diversity)
        cards.append(spec)
        apply_diversity(diversity, spec)
        seen.add(title)
    return cards


def effects_from_spec(
    spec_or_effect: dict | str,
    trigger: Optional[str] = None,
    ability_value: int = 0,
) -> tuple[Effect, Effect]:
    if isinstance(spec_or_effect, dict):
        effect_type = str(spec_or_effect.get("effect_type", "NONE"))
        trigger_type = str(spec_or_effect.get("trigger", "NO ABILITY"))
    else:
        effect_type = str(spec_or_effect)
        trigger_type = str(trigger or "NO ABILITY")

    _ = ability_value
    effect_type = effect_type.strip().upper()
    if effect_type == "BOOST":
        effect_type = "VITALITY"
    elif effect_type == "DRAIN":
        effect_type = "DAMAGE"
    effect = EFFECT_TYPE_TO_EFFECT.get(effect_type, Effect.NONE)
    trigger_norm = str(trigger_type or "NO ABILITY").strip().upper()

    if trigger_norm == "DEPLOY":
        return effect, Effect.NONE
    if trigger_norm.startswith("ON DEATH") or trigger_norm in {"DEATHWISH", "DEATHBLOW"}:
        return Effect.NONE, effect
    return Effect.NONE, Effect.NONE


def run_quality_gate(count_per_case: int = 2) -> bool:
    init_db()
    probes = [
        "Winston Churchill",
        "Albert Einstein",
        "Genghis Khan",
        "Napoleon",
        "Cleopatra",
    ]
    for title in probes:
        summary = _fetch_summary_from_api(title)
        if not summary:
            continue
        for _ in range(count_per_case):
            rarity = pick_random_rarity()
            spec = generate_card_spec(title, summary, rarity)
            valid, _ = _validate_spec(spec)
            if not valid:
                return False
    return True
