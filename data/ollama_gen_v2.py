"""WikiDeck historical-people generator.

This generator works only with a curated list of historical personalities and
always produces cards with theme ``LIVING``.
"""

from __future__ import annotations

import os
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

from config import DB_PATH, OLLAMA_HOST, OLLAMA_MAX_RETRIES, OLLAMA_MODEL
from core.effects import Effect
from data.card_contract import (
    normalize_nemesis,
    parse_json_block,
    sanitize_ability_text_value,
    validate_card_contract,
)
from data.db import get_cached_card, get_fallback_cached_card, init_db, save_card
from data.historical_people_pool import HISTORICAL_PERSONALITIES
from data.wikipedia import get_article

WIKI_SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
WIKI_PAGEVIEWS_API = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "en.wikipedia.org/all-access/user/{}/monthly/{}/{}"
)
HEADERS = {"User-Agent": "WikiDeck/2.0 (historical-cards)"}
REQUEST_TIMEOUT = 10
SUMMARY_MIN_CHARS = 120
MAX_SUMMARY_CHARS = 400
_OLLAMA_RUNTIME_AVAILABLE: Optional[bool] = None
_OLLAMA_DOWN_NOTIFIED = False
_OLLAMA_CLIENT = None
_OLLAMA_ACTIVE_HOST: Optional[str] = None
_OLLAMA_CHAT_LOCK = threading.Lock()


def _log(message: str) -> None:
    print(message, flush=True)

RARITY_WEIGHTS = {"COMMON": 70, "UNCOMMON": 20, "RARE": 8, "EPIC": 2, "LEGENDARY": 0}

RARITY_BUDGETS = {
    "COMMON": 2.0,
    "UNCOMMON": 2.4,
    "RARE": 2.8,
    "EPIC": 3.2,
    "LEGENDARY": 3.8,
}

HP_CAPS = {"COMMON": 4, "UNCOMMON": 5, "RARE": 6, "EPIC": 7, "LEGENDARY": 8}
BASE_SCORE_CAPS = {"COMMON": 4, "UNCOMMON": 5, "RARE": 6, "EPIC": 7, "LEGENDARY": 8}
MIN_STAT_FLOORS = {"COMMON": 2, "UNCOMMON": 2, "RARE": 3, "EPIC": 3, "LEGENDARY": 4}

ABILITY_COSTS = {
    "DAMAGE": 1.4,
    "EXECUTE": 1.8,
    "HEAL": 1.1,
    "APPLY_VIGOR": 1.1,
    "APPLY_PLAGUE": 1.5,
    "APPLY_DECAY": 1.4,
    "DRAW": 1.3,
    "APPLY_FLOURISH": 1.2,
    "REVIVE": 1.7,
    "BRIBE": 1.5,
    "GOLD": 1.2,
    "APPLY_SHIELD": 1.2,
    "APPLY_IMMUNITY": 1.6,
}

EFFECT_TYPE_TO_EFFECT = {
    "DAMAGE": Effect.DAMAGE_ENEMY_2,
    "EXECUTE": Effect.DAMAGE_ENEMY_2,
    "HEAL": Effect.HEAL_SELF_2,
    "APPLY_VIGOR": Effect.BUFF_SELF_1,
    "APPLY_PLAGUE": Effect.NONE,
    "APPLY_DECAY": Effect.NONE,
    "DRAW": Effect.DRAW_1,
    "APPLY_FLOURISH": Effect.BUFF_SELF_1,
    "REVIVE": Effect.NONE,
    "BRIBE": Effect.NONE,
    "GOLD": Effect.DRAW_1,
    "APPLY_SHIELD": Effect.HEAL_SELF_2,
    "APPLY_IMMUNITY": Effect.NONE,
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
    return ollama is not None


def _normalize_host(host: str) -> str:
    if not host:
        return "http://127.0.0.1:11434"
    fixed = host.strip().rstrip("/")
    if not fixed.startswith(("http://", "https://")):
        fixed = f"http://{fixed}"
    return fixed


def _host_candidates() -> list[str]:
    candidates = [_normalize_host(OLLAMA_HOST), "http://127.0.0.1:11434", "http://localhost:11434"]
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
        return ollama.Client(host=host)
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
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            return None
        data = response.json()
        if data.get("type") == "disambiguation":
            return None
        extract = (data.get("extract") or "").strip()
        if len(extract) < SUMMARY_MIN_CHARS:
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


def get_monthly_views(title: str) -> int:
    safe_title = quote(title.replace(" ", "_"), safe="")
    now = datetime.now(UTC)
    first_of_this_month = datetime(now.year, now.month, 1, tzinfo=UTC)
    last_of_prev_month = first_of_this_month - timedelta(days=1)
    first_of_prev_month = datetime(last_of_prev_month.year, last_of_prev_month.month, 1, tzinfo=UTC)
    start = first_of_prev_month.strftime("%Y%m%d00")
    end = last_of_prev_month.strftime("%Y%m%d00")
    url = WIKI_PAGEVIEWS_API.format(safe_title, start, end)
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            return 0
        data = response.json()
        items = data.get("items") or []
        if not items:
            return 0
        return int(items[-1].get("views", 0) or 0)
    except Exception:
        return 0


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
        if fallback and len(fallback[1].strip()) >= SUMMARY_MIN_CHARS and _looks_like_person(fallback[0], fallback[1]):
            views = get_monthly_views(fallback[0])
            rarity = assign_rarity_by_views(views)
            if pack_rarity is not None:
                _log(f"  -> {fallback[0]} | views: {views:,}/month | pack rarity: {pack_rarity}")
            else:
                _log(f"  -> Rarity: {rarity} ({views:,} views/month)")
            return fallback[0], fallback[1].strip(), rarity

    # Pool may be exhausted (all titles already in cards). In that case,
    # gracefully allow a repeat instead of hard failing generation.
    for title in pool_copy:
        fallback = get_article(title)
        if fallback and len(fallback[1].strip()) >= SUMMARY_MIN_CHARS and _looks_like_person(fallback[0], fallback[1]):
            views = get_monthly_views(fallback[0])
            rarity = assign_rarity_by_views(views)
            if pack_rarity is not None:
                _log(f"  -> {fallback[0]} | views: {views:,}/month | pack rarity: {pack_rarity}")
            else:
                _log(f"  -> Rarity: {rarity} ({views:,} views/month)")
            return fallback[0], fallback[1].strip(), rarity

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
        candidates.extend(["DAMAGE", "EXECUTE"])
    if hits.get("medicine", 0) or hits.get("disease", 0):
        candidates.extend(["HEAL", "APPLY_VIGOR"])
    if hits.get("assassin", 0) or hits.get("collapse", 0):
        candidates.extend(["APPLY_PLAGUE", "APPLY_DECAY"])
    if hits.get("education", 0):
        candidates.extend(["DRAW", "APPLY_FLOURISH", "APPLY_VIGOR", "GOLD"])
    if hits.get("culture", 0):
        candidates.extend(["APPLY_FLOURISH", "APPLY_VIGOR", "APPLY_SHIELD", "DRAW"])
    if hits.get("religion", 0):
        candidates.extend(["APPLY_FLOURISH", "REVIVE", "APPLY_VIGOR", "HEAL"])
    if hits.get("politics", 0) or hits.get("economy", 0):
        candidates.extend(["BRIBE", "GOLD"])
    if hits.get("fortress", 0):
        candidates.extend(["APPLY_SHIELD", "APPLY_IMMUNITY"])

    if not candidates:
        if theme == "LIVING":
            candidates = ["DRAW", "APPLY_FLOURISH", "APPLY_VIGOR", "HEAL", "GOLD", "APPLY_SHIELD"]
        else:
            candidates = ["APPLY_FLOURISH"]

    unique: list[str] = []
    for effect in candidates:
        if effect not in unique:
            unique.append(effect)
    return unique


def _trigger_candidates(effect_type: str) -> list[str]:
    if effect_type in {"DAMAGE", "EXECUTE", "APPLY_PLAGUE", "APPLY_DECAY", "BRIBE"}:
        return ["ON PLAY"]
    if effect_type in {"HEAL", "APPLY_VIGOR", "APPLY_SHIELD", "APPLY_IMMUNITY", "REVIVE"}:
        triggers = ["ON PLAY", "ON DEATH:self"]
        if effect_type in {"HEAL", "APPLY_VIGOR"}:
            triggers.append("ON DEATH:ally")
        return triggers
    if effect_type in {"DRAW", "GOLD", "APPLY_FLOURISH"}:
        triggers = ["ON PLAY", "ON DEATH:self"]
        if effect_type in {"GOLD", "APPLY_FLOURISH"}:
            triggers.append("ON DEATH:ally")
        return triggers
    return ["ON PLAY"]


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
    if effect_type in {"DAMAGE", "HEAL"}:
        return 1 if rarity == "COMMON" else 2
    if effect_type in {"DRAW", "GOLD"}:
        return 1 if rarity in {"COMMON", "UNCOMMON"} else 2
    if effect_type == "EXECUTE":
        return 3
    if effect_type == "APPLY_IMMUNITY":
        return 1 if rarity in {"COMMON", "UNCOMMON"} else 2
    return 0


def _ability_text_template(effect_type: str, value: int) -> str:
    if effect_type == "DAMAGE":
        return f"Deal {value} damage to one enemy card."
    if effect_type == "EXECUTE":
        return f"Destroy one enemy card with {value} or fewer HP."
    if effect_type == "HEAL":
        return f"Restore {value} HP to one friendly card."
    if effect_type == "APPLY_VIGOR":
        return "Apply VIGOR to one friendly card."
    if effect_type == "APPLY_PLAGUE":
        return "Apply PLAGUE to one enemy card."
    if effect_type == "APPLY_DECAY":
        return "Apply DECAY to one enemy card."
    if effect_type == "DRAW":
        return f"Draw {value} cards."
    if effect_type == "APPLY_FLOURISH":
        return "Apply FLOURISH to one friendly card."
    if effect_type == "REVIVE":
        return "Return one card from your discard pile to the field."
    if effect_type == "BRIBE":
        return "Disable one enemy card ability for 1 turn."
    if effect_type == "GOLD":
        return f"Gain {value} gold."
    if effect_type == "APPLY_SHIELD":
        return "Apply SHIELD to this card."
    if effect_type == "APPLY_IMMUNITY":
        return "Apply IMMUNITY to this card."
    return "Apply FLOURISH to one friendly card."


def _with_trigger_context(trigger: str, ability_text: str) -> str:
    stripped = ability_text.strip()
    if trigger == "ON DEATH:self":
        body = stripped[0].lower() + stripped[1:] if stripped else stripped
        return f"When this card dies, {body}"
    if trigger == "ON DEATH:ally":
        body = stripped[0].lower() + stripped[1:] if stripped else stripped
        return f"When an ally dies, {body}"
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

    candidates = _effect_candidates(hits, theme="LIVING")
    filtered_candidates = [effect for effect in candidates if effect not in avoid_effects]
    if not filtered_candidates:
        filtered_candidates = candidates
    effect_type = _choose_with_diversity(filtered_candidates, effect_bucket, total, max_share=0.35)
    trigger = _choose_with_diversity(
        _trigger_candidates(effect_type),
        trigger_bucket,
        total,
        max_share=0.75,
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
        "source_type": "WIKIPEDIA",
        "source_ref": title,
        "summary_snippet": summary[:MAX_SUMMARY_CHARS],
    }


def build_system_prompt() -> str:
    return (
        "You are writing flavor text for WikiDeck cards.\n"
        "Each card is a real historical person. Your job is to write\n"
        "ONE ability sentence that reflects what this person actually\n"
        "did in history, using the pre-selected game mechanic.\n\n"
        "Rules for ability_text:\n"
        "- Under 20 words\n"
        "- Must contain ONLY mechanic and target (no explanations, no flavor)\n"
        "- One verb, one target, period\n"
        "- Only use these game terms: HP, Score, PLAGUE, VIGOR, DECAY,\n"
        "  FLOURISH, SHIELD, IMMUNITY, gold, cards\n"
        "FORBIDDEN words - never use these in ability_text:\n"
        "attack, defense, morale, faith, influence, power, strength, mana\n"
        "- If trigger is ON DEATH:self, ability_text MUST start with:\n"
        '  "When this card dies, ..."\n'
        "- If trigger is ON DEATH:ally, ability_text MUST start with:\n"
        '  "When an ally dies, ..."\n'
        "- Never write card names in ability_text (forbidden: 'When Frida Kahlo dies, ...')\n"
        "- For all other triggers, do not include trigger words in ability_text\n"
        "- One effect only - never combine two effects in one sentence\n"
        "- Complete sentence with a period\n\n"
        "Wrong format examples:\n"
        '- "On death, apply VIGOR to all friendly cards."\n'
        '- "On death, self -> REVIVE."\n'
        '- "Apply SHIELD representing defense in the realm of music."\n\n'
        '- "Apply SHIELD representing strategic defense."\n'
        '- "Deal 2 damage through military power."\n'
        '- "Gain 1 gold through political influence."\n\n'
        "Correct format examples:\n"
        '- "Apply VIGOR to all friendly cards."\n'
        '- "When an ally dies, apply FLOURISH to all friendly cards."\n'
        '- "Apply SHIELD to this card."\n'
        '- "Apply PLAGUE to all enemy cards."\n'
        '- "Apply DECAY to one enemy card."\n'
        '- "Deal 2 damage to one enemy card."\n'
        '- "Return one card from your discard pile to the field."\n'
        '- "Destroy one enemy card with 3 or fewer HP."\n'
        '- "Gain 1 gold."\n\n'
        "EXECUTE rule:\n"
        "- ability_value must exactly equal the number in ability_text\n"
        "- For EXECUTE, ability_value cannot be 0\n\n"
        "Rules for nemesis:\n"
        "- A real Wikipedia article title of a historical rival or opponent\n"
        "- Must be someone this person actually opposed in real history\n"
        "- Write null if no clear historical nemesis exists\n\n"
        "Return ONLY this JSON:\n"
        "{\n"
        '  "title": "EXACT Person value from the user prompt",\n'
        '  "rationale": "one sentence why this mechanic fits this person",\n'
        '  "ability_text": "...",\n'
        '  "nemesis": null\n'
        "}"
    )


def build_user_prompt(spec: dict, summary: str) -> str:
    return (
        f"Person: {spec['title']}\n"
        f"Required title echo: {spec['title']}\n"
        f"Summary: {summary[:MAX_SUMMARY_CHARS]}\n"
        f"Epoch: {spec['epoch']}\n"
        f"Mechanic: {spec['trigger']} -> {spec['effect_type']}\n"
        f"REQUIRED effect in ability_text: {spec['effect_type']}\n"
        f"Ability value: {spec['ability_value']}\n\n"
        "Examples of correct ability_text for different mechanics:\n"
        'DAMAGE: "Deal 2 damage to one enemy card."\n'
        'APPLY_PLAGUE: "Apply PLAGUE to all enemy cards."\n'
        'APPLY_FLOURISH: "Apply FLOURISH to all friendly cards."\n'
        'HEAL: "Restore 2 HP to one friendly card."\n'
        'DRAW: "Draw 2 cards."\n'
        'GOLD: "Gain 2 gold."\n'
        'EXECUTE: "Destroy one enemy card with 3 or fewer HP."\n'
        'APPLY_SHIELD: "Apply SHIELD to this card."\n'
        'BRIBE: "Disable one enemy card ability for 1 turn."\n'
        'REVIVE: "Return one card from your discard pile to the field."\n'
        'ON DEATH:ally context: "When an ally dies, apply FLOURISH to all friendly cards."'
    )


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
        if trigger == "ON DEATH:self" and not low.startswith("when this card dies,"):
            raise ValueError("ON DEATH:self ability_text must start with 'When this card dies,'")
        if trigger == "ON DEATH:ally" and not low.startswith("when an ally dies,"):
            raise ValueError("ON DEATH:ally ability_text must start with 'When an ally dies,'")
        return True, []
    except Exception as exc:
        return False, [str(exc)]


def _generate_flavor(spec: dict, summary: str, retries: int = 4) -> dict:
    global _OLLAMA_RUNTIME_AVAILABLE, _OLLAMA_DOWN_NOTIFIED
    fallback = {
        "title": spec["title"],
        "rationale": f"{spec['title']} is represented by {spec['effect_type']} based on known historical impact.",
        "ability_text": spec["ability_text"],
        "nemesis": None,
    }
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
    for attempt in range(1, retries + 1):
        user_prompt = build_user_prompt(spec, summary)
        if previous_errors:
            error_lines = "\n".join(f"- {item}" for item in previous_errors[-3:])
            user_prompt += f"\n\nPrevious issues to fix:\n{error_lines}"
        try:
            chat_payload = {
                "model": OLLAMA_MODEL,
                "format": "json",
                "options": {"temperature": 0},
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

            candidate = dict(spec)
            candidate["ability_text"] = parsed["ability_text"]
            candidate["nemesis"] = parsed["nemesis"]
            valid, errors = _validate_spec(candidate)
            if valid:
                return parsed
            previous_errors.extend(errors)
            print(f"[ai] invalid response for {spec['title']}: {errors}", flush=True)
        except Exception as exc:
            msg = str(exc)
            if "Failed to connect to Ollama" in msg or "Connection refused" in msg:
                reconnected = False
                for reconnect_try in range(max(1, OLLAMA_MAX_RETRIES)):
                    with _OLLAMA_CHAT_LOCK:
                        ok = _ensure_ollama_runtime()
                    if ok:
                        reconnected = True
                        _OLLAMA_RUNTIME_AVAILABLE = True
                        _OLLAMA_DOWN_NOTIFIED = False
                        print(f"[ai] reconnect success ({reconnect_try + 1}/{max(1, OLLAMA_MAX_RETRIES)})", flush=True)
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


def _balance_card(spec: dict) -> dict:
    rarity = spec["rarity"]
    budget = RARITY_BUDGETS.get(rarity, 2.0)
    floor = MIN_STAT_FLOORS.get(rarity, 1)

    effect_type = spec["effect_type"]
    value = int(spec.get("ability_value", 0) or 0)
    cost = ABILITY_COSTS.get(effect_type, 1.0)

    trigger = spec.get("trigger", "ON PLAY")
    if trigger.startswith("ON DEATH"):
        cost += 0.2
    elif trigger == "PASSIVE":
        cost += 0.3

    hp = max(floor, min(HP_CAPS.get(rarity, 5), round(1.2 + budget - 0.6 * cost)))
    base_score = max(floor, min(BASE_SCORE_CAPS.get(rarity, 5), round(1.0 + budget - 0.4 * cost + 0.12 * value)))
    spec["hp"] = int(hp)
    spec["base_score"] = int(base_score)
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
        flavor = _generate_flavor(spec, summary)
        spec["rationale"] = flavor["rationale"]
        spec["ability_text"] = sanitize_ability_text_value(flavor["ability_text"], int(spec["ability_value"]))
        spec["nemesis"] = flavor["nemesis"]

        valid, errors = _validate_spec(spec)
        if not valid:
            if attempt >= 6:
                raise ValueError(f"Invalid card contract for {title}: {errors}")
            print(f"[gen] retry {attempt}/6 invalid: {title} -> {errors[0]}", flush=True)
            continue

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
            f"HP={spec['hp']} SC={spec['base_score']}",
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
        '    "base_score": %d,\n'
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
            int(spec["base_score"]),
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
    effect = EFFECT_TYPE_TO_EFFECT.get(effect_type, Effect.NONE)
    if trigger_type == "ON PLAY":
        return effect, Effect.NONE
    if trigger_type.startswith("ON DEATH"):
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
