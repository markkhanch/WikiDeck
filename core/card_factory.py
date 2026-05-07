"""Helpers for building Card objects from cached specs or raw fields."""
from __future__ import annotations

import re

from core.card import Card
from core.effects import Effect
from data.db import get_or_fetch_article, get_or_fetch_image
from data.wikipedia import fetch_media_image_url
from data.ollama_gen import effects_from_spec


def _effect_type_from_runtime(on_play: Effect, on_death: Effect) -> str:
    if on_play == Effect.DAMAGE_ENEMY_2 or on_death == Effect.DAMAGE_ENEMY_2:
        return "DAMAGE"
    if on_play == Effect.HEAL_SELF_2 or on_death == Effect.HEAL_SELF_2:
        return "HEAL"
    if on_play == Effect.DRAW_1 or on_death == Effect.DRAW_1:
        return "DRAW"
    if on_play == Effect.BUFF_SELF_1 or on_death == Effect.BUFF_SELF_1:
        return "VITALITY"
    return "NONE"


def _normalize_effect_type(effect_type: str) -> str:
    normalized = str(effect_type or "").strip().upper()
    if normalized == "BOOST":
        return "VITALITY"
    if normalized == "DRAIN":
        return "DAMAGE"
    return normalized or "NONE"


def _ability_value_for_effect(effect_type: str) -> int:
    if effect_type in {"DAMAGE", "VITALITY"}:
        return 2
    if effect_type == "DRAW":
        return 1
    return 0


def _ability_text_for_effect(effect_type: str, value: int) -> str:
    if effect_type == "DAMAGE":
        return f"Deal {max(1, value)} damage to one enemy card."
    if effect_type == "VITALITY":
        return f"Give this card Vitality for {max(1, value)} turns."
    return ""


def build_card(
    title: str,
    theme: str,
    hp: int,
    on_play: Effect,
    on_death: Effect,
    *,
    rarity: str = "COMMON",
    epoch: str = "TIMELESS",
    nemesis: str | None = None,
    ability_text: str = "",
    ability_trigger: str = "",
    trigger_value: int = 0,
    effect_type: str = "",
    ability_value: int = 0,
) -> Card:
    requested_effect_type = effect_type.strip().upper()
    resolved_effect_type = (
        _normalize_effect_type(requested_effect_type)
        if requested_effect_type
        else _effect_type_from_runtime(on_play, on_death)
    )
    resolved_trigger = ability_trigger.strip() or (
        "DEPLOY" if on_play != Effect.NONE else "DEATHWISH" if on_death != Effect.NONE else "NO ABILITY"
    )
    resolved_value = int(ability_value) if int(ability_value or 0) > 0 else _ability_value_for_effect(resolved_effect_type)
    normalized_ability_text = str(ability_text or "")
    if requested_effect_type in {"BOOST", "DRAIN"} and (
        not normalized_ability_text.strip() or re.search(r"\b(boost|drain)\b", normalized_ability_text, re.IGNORECASE)
    ):
        normalized_ability_text = _ability_text_for_effect(resolved_effect_type, resolved_value)
    data = get_or_fetch_article(title)
    if data is None:
        media_url = fetch_media_image_url(title)
        image = get_or_fetch_image(title, media_url)
        return Card(
            title=title,
            theme=theme,
            hp=hp,
            description="(offline)",
            image=image,
            on_play=on_play,
            on_death=on_death,
            rarity=rarity,
            epoch=epoch,
            nemesis=nemesis,
            ability_text=normalized_ability_text,
            ability_trigger=resolved_trigger,
            trigger_value=int(trigger_value or 0),
            effect_type=resolved_effect_type,
            ability_value=resolved_value,
            max_hp=hp,
        )
    image = get_or_fetch_image(data["title"], data["thumbnail"])
    if image is None:
        media_url = fetch_media_image_url(data["title"])
        image = get_or_fetch_image(data["title"], media_url)
    return Card(
        title=data["title"],
        description=data["description"],
        extract=data["extract"],
        image=image,
        hp=hp,
        theme=theme,
        rarity=rarity,
        epoch=epoch,
        nemesis=nemesis,
        ability_text=normalized_ability_text,
        ability_trigger=resolved_trigger,
        trigger_value=int(trigger_value or 0),
        effect_type=resolved_effect_type,
        ability_value=resolved_value,
        max_hp=hp,
        on_play=on_play,
        on_death=on_death,
    )


def build_card_from_spec(spec: dict) -> Card:
    on_play, on_death = effects_from_spec(spec)
    return build_card(
        spec["title"],
        spec["theme"],
        spec["hp"],
        on_play,
        on_death,
        rarity=spec.get("rarity", "COMMON"),
        epoch=spec.get("epoch", "TIMELESS"),
        nemesis=spec.get("nemesis"),
        ability_text=spec.get("ability_text", ""),
        ability_trigger=spec.get("trigger", ""),
        trigger_value=int(spec.get("trigger_value", 0) or 0),
        effect_type=spec.get("effect_type", "NONE"),
        ability_value=int(spec.get("ability_value", 0) or 0),
    )
