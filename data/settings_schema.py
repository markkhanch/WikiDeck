from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from config import (
    DECK_MAX,
    DECK_MIN,
    DECK_TARGET,
    FIELD_LIMIT,
    FPS,
    OLLAMA_HOST,
    OLLAMA_MAX_RETRIES,
    OLLAMA_MODEL,
    STARTING_HAND_SIZE,
    USE_OLLAMA_GENERATOR,
)

SettingType = Literal["bool", "int", "float", "str"]

CATEGORY_GENERAL = "General"
CATEGORY_GAMEPLAY = "Gameplay"
CATEGORY_SHOP = "Shop"
CATEGORY_AI = "AI"
CATEGORY_NETWORK = "Network"
CATEGORY_ADVANCED = "Advanced"

CATEGORY_ORDER = (
    CATEGORY_GENERAL,
    CATEGORY_GAMEPLAY,
    CATEGORY_SHOP,
    CATEGORY_AI,
    CATEGORY_NETWORK,
    CATEGORY_ADVANCED,
)

RARITIES = ("COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY")
PACK_ORDER = ("basic", "premium", "epic", "legendary")
PACK_DISPLAY_NAMES = {
    "basic": "Basic",
    "premium": "Premium",
    "epic": "Epic",
    "legendary": "Legendary",
}

PACK_TYPES_DEFAULT: dict[str, dict[str, Any]] = {
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

SINGLE_PRICES_DEFAULT = {
    "COMMON": 30,
    "UNCOMMON": 75,
    "RARE": 150,
    "EPIC": 400,
    "LEGENDARY": 1000,
}

SINGLE_RARITY_WEIGHTS_DEFAULT = {"COMMON": 55, "UNCOMMON": 25, "RARE": 13, "EPIC": 6, "LEGENDARY": 1}


@dataclass(frozen=True)
class SettingDefinition:
    key: str
    label: str
    category: str
    value_type: SettingType
    default: Any
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    apply_scope: Literal["live", "menu", "restart"] = "live"
    advanced: bool = False


def _make_shop_pack_definitions() -> list[SettingDefinition]:
    out: list[SettingDefinition] = []
    for pack in PACK_ORDER:
        display = PACK_DISPLAY_NAMES[pack]
        defaults = PACK_TYPES_DEFAULT[pack]
        out.append(
            SettingDefinition(
                key=f"shop.pack.{pack}.price",
                label=f"{display} pack price",
                category=CATEGORY_SHOP,
                value_type="int",
                default=int(defaults["price"]),
                min_value=1,
                max_value=5000,
                step=5,
            )
        )
        out.append(
            SettingDefinition(
                key=f"shop.pack.{pack}.size",
                label=f"{display} pack size",
                category=CATEGORY_SHOP,
                value_type="int",
                default=int(defaults["size"]),
                min_value=1,
                max_value=20,
                step=1,
                apply_scope="menu",
            )
        )
        weights = dict(defaults["weights"])
        for rarity in RARITIES:
            out.append(
                SettingDefinition(
                    key=f"shop.pack.{pack}.weight.{rarity.lower()}",
                    label=f"{display} {rarity} weight",
                    category=CATEGORY_SHOP,
                    value_type="int",
                    default=int(weights[rarity]),
                    min_value=0,
                    max_value=100,
                    step=1,
                )
            )
    for rarity in RARITIES:
        out.append(
            SettingDefinition(
                key=f"shop.single.price.{rarity.lower()}",
                label=f"Single {rarity} price",
                category=CATEGORY_SHOP,
                value_type="int",
                default=int(SINGLE_PRICES_DEFAULT[rarity]),
                min_value=1,
                max_value=10000,
                step=5,
            )
        )
        out.append(
            SettingDefinition(
                key=f"shop.single.weight.{rarity.lower()}",
                label=f"Single {rarity} rarity weight",
                category=CATEGORY_SHOP,
                value_type="int",
                default=int(SINGLE_RARITY_WEIGHTS_DEFAULT[rarity]),
                min_value=0,
                max_value=100,
                step=1,
                advanced=True,
            )
        )
    return out


SETTINGS_DEFINITIONS: tuple[SettingDefinition, ...] = tuple(
    [
        SettingDefinition(
            key="display.fullscreen",
            label="Fullscreen",
            category=CATEGORY_GENERAL,
            value_type="bool",
            default=False,
            apply_scope="live",
        ),
        SettingDefinition(
            key="display.target_fps",
            label="Target FPS",
            category=CATEGORY_GENERAL,
            value_type="int",
            default=int(FPS),
            min_value=30,
            max_value=240,
            step=5,
            apply_scope="live",
        ),
        SettingDefinition(
            key="display.ui_scale",
            label="UI scale",
            category=CATEGORY_GENERAL,
            value_type="float",
            default=1.0,
            min_value=0.75,
            max_value=1.5,
            step=0.05,
            apply_scope="menu",
        ),
        SettingDefinition(
            key="display.animations",
            label="Enable UI animations",
            category=CATEGORY_GENERAL,
            value_type="bool",
            default=True,
            apply_scope="live",
        ),
        SettingDefinition(
            key="gameplay.starting_hand_size",
            label="Starting hand size",
            category=CATEGORY_GAMEPLAY,
            value_type="int",
            default=int(STARTING_HAND_SIZE),
            min_value=1,
            max_value=15,
            step=1,
            apply_scope="menu",
        ),
        SettingDefinition(
            key="gameplay.field_limit",
            label="Field limit per player",
            category=CATEGORY_GAMEPLAY,
            value_type="int",
            default=int(FIELD_LIMIT),
            min_value=1,
            max_value=30,
            step=1,
            apply_scope="menu",
        ),
        SettingDefinition(
            key="gameplay.deck_min",
            label="Deck minimum",
            category=CATEGORY_GAMEPLAY,
            value_type="int",
            default=int(DECK_MIN),
            min_value=1,
            max_value=60,
            step=1,
            apply_scope="menu",
        ),
        SettingDefinition(
            key="gameplay.deck_target",
            label="Deck auto-fill target",
            category=CATEGORY_GAMEPLAY,
            value_type="int",
            default=int(DECK_TARGET),
            min_value=1,
            max_value=60,
            step=1,
            apply_scope="menu",
        ),
        SettingDefinition(
            key="gameplay.deck_max",
            label="Deck maximum",
            category=CATEGORY_GAMEPLAY,
            value_type="int",
            default=int(DECK_MAX),
            min_value=1,
            max_value=80,
            step=1,
            apply_scope="menu",
        ),
        SettingDefinition(
            key="ai.use_ollama",
            label="Use Ollama generator",
            category=CATEGORY_AI,
            value_type="bool",
            default=bool(USE_OLLAMA_GENERATOR),
            apply_scope="live",
        ),
        SettingDefinition(
            key="ai.ollama_host",
            label="Ollama host URL",
            category=CATEGORY_AI,
            value_type="str",
            default=str(OLLAMA_HOST),
            apply_scope="live",
        ),
        SettingDefinition(
            key="ai.ollama_model",
            label="Ollama model",
            category=CATEGORY_AI,
            value_type="str",
            default=str(OLLAMA_MODEL),
            apply_scope="live",
        ),
        SettingDefinition(
            key="ai.ollama_max_retries",
            label="Ollama reconnect retries",
            category=CATEGORY_AI,
            value_type="int",
            default=int(OLLAMA_MAX_RETRIES),
            min_value=1,
            max_value=20,
            step=1,
            apply_scope="live",
        ),
        SettingDefinition(
            key="ai.temperature",
            label="LLM temperature",
            category=CATEGORY_ADVANCED,
            value_type="float",
            default=0.0,
            min_value=0.0,
            max_value=1.0,
            step=0.05,
            advanced=True,
        ),
        SettingDefinition(
            key="ai.request_timeout",
            label="AI request timeout (sec)",
            category=CATEGORY_ADVANCED,
            value_type="int",
            default=10,
            min_value=1,
            max_value=120,
            step=1,
            advanced=True,
        ),
        SettingDefinition(
            key="ai.summary_min_chars",
            label="Summary min chars",
            category=CATEGORY_ADVANCED,
            value_type="int",
            default=120,
            min_value=20,
            max_value=2000,
            step=10,
            advanced=True,
        ),
        SettingDefinition(
            key="ai.summary_max_chars",
            label="Summary max chars",
            category=CATEGORY_ADVANCED,
            value_type="int",
            default=400,
            min_value=20,
            max_value=4000,
            step=10,
            advanced=True,
        ),
        SettingDefinition(
            key="network.host_bind",
            label="Server bind host",
            category=CATEGORY_NETWORK,
            value_type="str",
            default="0.0.0.0",
            apply_scope="restart",
        ),
        SettingDefinition(
            key="network.default_ports",
            label="Default ports (comma-separated)",
            category=CATEGORY_NETWORK,
            value_type="str",
            default="8765,8766,8767",
            apply_scope="restart",
        ),
        SettingDefinition(
            key="debug.match_verbose_logs",
            label="Verbose match logs",
            category=CATEGORY_ADVANCED,
            value_type="bool",
            default=True,
            advanced=True,
        ),
        SettingDefinition(
            key="debug.network_verbose_logs",
            label="Verbose network logs",
            category=CATEGORY_ADVANCED,
            value_type="bool",
            default=True,
            advanced=True,
        ),
    ]
    + _make_shop_pack_definitions()
)

SETTINGS_BY_KEY = {item.key: item for item in SETTINGS_DEFINITIONS}


def defaults_map() -> dict[str, Any]:
    return {item.key: item.default for item in SETTINGS_DEFINITIONS}
