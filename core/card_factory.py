"""Helpers for building Card objects from cached specs or raw fields."""
from __future__ import annotations

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
        return "APPLY_FLOURISH"
    return "NONE"


def _ability_value_for_effect(effect_type: str) -> int:
    if effect_type in {"DAMAGE", "HEAL"}:
        return 2
    if effect_type == "DRAW":
        return 1
    return 0


def build_card(
    title: str,
    theme: str,
    hp: int,
    base_score: int,
    on_play: Effect,
    on_death: Effect,
    *,
    rarity: str = "COMMON",
    ability_text: str = "",
    ability_trigger: str = "",
    effect_type: str = "",
    ability_value: int = 0,
) -> Card:
    resolved_effect_type = effect_type.strip().upper() or _effect_type_from_runtime(on_play, on_death)
    resolved_trigger = ability_trigger.strip() or (
        "ON PLAY" if on_play != Effect.NONE else "ON DEATH:self" if on_death != Effect.NONE else "NO ABILITY"
    )
    resolved_value = int(ability_value) if int(ability_value or 0) > 0 else _ability_value_for_effect(resolved_effect_type)
    data = get_or_fetch_article(title)
    if data is None:
        media_url = fetch_media_image_url(title)
        image = get_or_fetch_image(title, media_url)
        return Card(
            title=title,
            theme=theme,
            hp=hp,
            base_score=base_score,
            description="(offline)",
            image=image,
            on_play=on_play,
            on_death=on_death,
            rarity=rarity,
            ability_text=ability_text,
            ability_trigger=resolved_trigger,
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
        base_score=base_score,
        theme=theme,
        rarity=rarity,
        ability_text=ability_text,
        ability_trigger=resolved_trigger,
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
        spec["base_score"],
        on_play,
        on_death,
        rarity=spec.get("rarity", "COMMON"),
        ability_text=spec.get("ability_text", ""),
        ability_trigger=spec.get("trigger", ""),
        effect_type=spec.get("effect_type", "NONE"),
        ability_value=int(spec.get("ability_value", 0) or 0),
    )
