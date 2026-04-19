"""Public generator API.

Project generation is historical-personality-only and implemented in V2.
This module stays as a compatibility import surface.
"""

from data.ollama_gen_v2 import (
    EFFECT_TYPE_TO_EFFECT,
    RARITY_BUDGETS,
    apply_diversity,
    build_grounded_spec,
    build_system_prompt,
    build_user_prompt,
    diversity_allows,
    effects_from_spec,
    generate_card_response,
    generate_card_spec,
    generate_card_specs,
    get_article_from_pool,
    get_monthly_views,
    ollama_available,
    parse_card_response,
    pick_random_rarity,
    run_quality_gate,
    assign_rarity_by_views,
)

__all__ = [
    "EFFECT_TYPE_TO_EFFECT",
    "RARITY_BUDGETS",
    "apply_diversity",
    "build_grounded_spec",
    "build_system_prompt",
    "build_user_prompt",
    "diversity_allows",
    "effects_from_spec",
    "generate_card_response",
    "generate_card_spec",
    "generate_card_specs",
    "get_article_from_pool",
    "get_monthly_views",
    "ollama_available",
    "parse_card_response",
    "pick_random_rarity",
    "run_quality_gate",
    "assign_rarity_by_views",
]
