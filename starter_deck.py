"""Hardcoded starter deck — 20 cards, all seven themes (GDD §7.1).

Tuple: (title, theme, hp, base_score, on_play, on_death).
Titles must match real Wikipedia article titles — spaces are URL-encoded
downstream, so "Albert Einstein" is fine. All cards are COMMON rarity for
now; rarer cards show up when booster packs and balance_card() land.
"""
from typing import List, Tuple

from core.effects import Effect

# (title, theme, hp, base_score, on_play, on_death)
StarterEntry = Tuple[str, str, int, int, Effect, Effect]

STARTER_CARDS: List[StarterEntry] = [
    # LIVING — people
    ("Albert Einstein",        "LIVING",     3, 4, Effect.DRAW_1,         Effect.NONE),
    ("Charles Darwin",         "LIVING",     4, 3, Effect.NONE,           Effect.DRAW_1),
    ("William Shakespeare",    "LIVING",     3, 3, Effect.NONE,           Effect.NONE),

    # PLACES — tanky, low damage
    ("Moon",                   "PLACES",     4, 3, Effect.NONE,           Effect.NONE),
    ("Mount Everest",          "PLACES",     6, 2, Effect.NONE,           Effect.NONE),
    ("Pacific Ocean",          "PLACES",     7, 1, Effect.HEAL_SELF_2,    Effect.NONE),

    # EVENTS — aggressive
    ("World War II",           "EVENTS",     3, 5, Effect.DAMAGE_ENEMY_2, Effect.NONE),
    ("French Revolution",      "EVENTS",     4, 4, Effect.NONE,           Effect.DAMAGE_ENEMY_2),
    ("Renaissance",            "EVENTS",     4, 3, Effect.BUFF_SELF_1,    Effect.NONE),

    # SCIENCE — three so CONFLUENCE can fire naturally
    ("Fire",                   "SCIENCE",    4, 3, Effect.DAMAGE_ENEMY_2, Effect.NONE),
    ("Water",                  "SCIENCE",    5, 2, Effect.NONE,           Effect.NONE),
    ("Sun",                    "SCIENCE",    3, 4, Effect.NONE,           Effect.NONE),

    # TECHNOLOGY — card draw / utility
    ("Computer",               "TECHNOLOGY", 3, 4, Effect.DRAW_1,         Effect.NONE),
    ("Internet",               "TECHNOLOGY", 2, 5, Effect.DRAW_1,         Effect.NONE),
    ("Wheel",                  "TECHNOLOGY", 4, 2, Effect.NONE,           Effect.NONE),

    # CULTURE
    ("Jazz",                   "CULTURE",    3, 3, Effect.NONE,           Effect.NONE),
    ("Great Pyramid of Giza",  "CULTURE",    6, 2, Effect.NONE,           Effect.NONE),

    # CONCEPTS
    ("Democracy",              "CONCEPTS",   5, 2, Effect.NONE,           Effect.NONE),
    ("Gravity",                "CONCEPTS",   4, 3, Effect.BUFF_SELF_1,    Effect.NONE),
    ("Time",                   "CONCEPTS",   3, 3, Effect.NONE,           Effect.DRAW_1),
]
