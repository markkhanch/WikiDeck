from __future__ import annotations

import json
import re
from typing import Optional

ALLOWED_THEMES = {
    "LIVING",
    "PLACES",
    "EVENTS",
    "SCIENCE",
    "TECHNOLOGY",
    "CULTURE",
    "CONCEPTS",
}
ALLOWED_EPOCHS = {
    "ANCIENT",
    "MEDIEVAL",
    "EARLY_MODERN",
    "MODERN",
    "CONTEMPORARY",
    "TIMELESS",
}
ALLOWED_TRIGGERS = {
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
ALLOWED_EFFECTS = {
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
    "REVIVE",
    "NONE",
}

# Only these are truly wired to gameplay in core/effects.py.
GAMEPLAY_SUPPORTED_EFFECTS = {
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
    "REVIVE",
    "NONE",
}
GAMEPLAY_SUPPORTED_TRIGGERS = ALLOWED_TRIGGERS

NUMBERED_EFFECTS = {
    "DAMAGE",
    "BLEEDING",
    "VITALITY",
    "DRAW",
    "DISCARD",
}
NUMBERLESS_EFFECTS = {
    "POISON",
    "DESTROY",
    "BANISH",
    "HEAL",
    "SHIELD",
    "IMMUNITY",
    "LOCK",
    "VEIL",
    "DOOMED",
    "DUEL",
    "CLASH",
    "REVIVE",
    "NONE",
}

FORBIDDEN_WORDS = {
    "attack",
    "defense",
    "morale",
    "faith",
    "influence",
    "power",
    "strength",
    "mana",
}

EFFECT_KEYWORDS = {
    "DAMAGE": {"damage", "deal"},
    "HEAL": {"heal", "restore"},
    "DRAW": {"draw"},
    "BLEEDING": {"bleeding"},
    "VITALITY": {"vitality"},
    "POISON": {"poison"},
    "SHIELD": {"shield"},
    "IMMUNITY": {"immunity"},
    "LOCK": {"lock"},
    "VEIL": {"veil"},
    "DESTROY": {"destroy"},
    "BANISH": {"banish"},
    "DUEL": {"duel"},
    "CLASH": {"clash"},
    "REVIVE": {"return", "discard pile"},
}

_FIRST_INT_RE = re.compile(r"\b\d+\b")


def parse_json_block(raw: str) -> dict:
    clean = (raw or "").strip()
    clean = clean.removeprefix("```json").removeprefix("```").strip()
    clean = clean.removesuffix("```").strip()
    obj = json.loads(clean)
    if not isinstance(obj, dict):
        raise ValueError("Response is not a JSON object")
    return obj


def normalize_nemesis(value: object) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed or trimmed.lower() in {"null", "none", "n/a"}:
        return None
    return trimmed


# Map English number words to digits so LLM responses with "two cards" still
# pass the numeric-value contract check.
_WORD_NUMBERS: dict[str, str] = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12",
}
_WORD_NUMBER_RE = re.compile(
    r"\b(" + "|".join(_WORD_NUMBERS.keys()) + r")\b",
    re.IGNORECASE,
)


def _replace_word_numbers_with_digits(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return _WORD_NUMBERS[match.group(1).lower()]
    return _WORD_NUMBER_RE.sub(repl, text)


def sanitize_ability_text_value(text: str, value: int) -> str:
    if not text:
        return text
    # First, convert English number-words ("two") to digits so the regex can match.
    text = _replace_word_numbers_with_digits(text)
    # If the LLM omitted a number entirely but the effect needs one, inject it
    # in front of the first "card"/"cards" token so the result still reads well.
    if not _FIRST_INT_RE.search(text):
        injected = re.sub(r"\b(cards?|enemy|allied)\b", f"{value} \\1", text, count=1)
        if injected != text:
            return injected
        return text
    return _FIRST_INT_RE.sub(str(value), text, count=1)


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9_]+", text or ""))


def _contains_forbidden(text: str) -> bool:
    low = (text or "").lower()
    return any(word in low for word in FORBIDDEN_WORDS)


def _has_multi_effect(text: str) -> bool:
    low = (text or "").lower()
    if low.count(".") > 1:
        return True
    # Common "two effects in one text" connectors.
    return " and " in low and ("draw" in low or "damage" in low or "restore" in low or "apply " in low)


def ability_text_valid(text: str, effect_type: str, ability_value: int) -> bool:
    if not text:
        return False
    stripped = text.strip()
    if not stripped.endswith("."):
        return False
    if _word_count(stripped) > 20:
        return False
    if _contains_forbidden(stripped):
        return False
    if _has_multi_effect(stripped):
        return False

    low = stripped.lower()
    if effect_type in NUMBERED_EFFECTS:
        nums = [int(n) for n in re.findall(r"\b\d+\b", stripped)]
        if not nums or nums[0] != int(ability_value):
            return False
    if effect_type in NUMBERLESS_EFFECTS and int(ability_value) != 0:
        return False

    keys = EFFECT_KEYWORDS.get(effect_type)
    if keys and not any(k in low for k in keys):
        return False
    return True


def validate_card_contract(card: dict, *, strict_gameplay: bool = False) -> None:
    required = {
        "theme",
        "epoch",
        "trigger",
        "trigger_value",
        "effect_type",
        "ability_text",
        "ability_value",
        "nemesis",
    }
    missing = sorted(required - set(card.keys()))
    if missing:
        raise ValueError(f"Missing fields: {', '.join(missing)}")

    if card["theme"] not in ALLOWED_THEMES:
        raise ValueError(f"Invalid theme: {card['theme']}")
    if card["epoch"] not in ALLOWED_EPOCHS:
        raise ValueError(f"Invalid epoch: {card['epoch']}")
    if card["trigger"] not in ALLOWED_TRIGGERS:
        raise ValueError(f"Invalid trigger: {card['trigger']}")
    if card["effect_type"] not in ALLOWED_EFFECTS:
        raise ValueError(f"Invalid effect_type: {card['effect_type']}")
    if int(card.get("ability_value", 0)) < 0:
        raise ValueError("ability_value cannot be negative")
    if card["effect_type"] in NUMBERED_EFFECTS and int(card.get("ability_value", 0)) <= 0:
        raise ValueError("ability_value must be > 0 for numbered effects")

    if strict_gameplay:
        if card["trigger"] not in GAMEPLAY_SUPPORTED_TRIGGERS:
            raise ValueError(f"Unsupported trigger for gameplay: {card['trigger']}")
        if card["effect_type"] not in GAMEPLAY_SUPPORTED_EFFECTS:
            raise ValueError(f"Unsupported effect for gameplay: {card['effect_type']}")

    if card["trigger"] not in {"TIMER", "ADRENALINE", "BLOODTHIRST"}:
        card["trigger_value"] = 0
    if card["effect_type"] in NUMBERLESS_EFFECTS:
        card["ability_value"] = 0

    if not ability_text_valid(card.get("ability_text", ""), card["effect_type"], int(card.get("ability_value", 0))):
        raise ValueError("ability_text failed contract validation")

    card["nemesis"] = normalize_nemesis(card.get("nemesis"))
