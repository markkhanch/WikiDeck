from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any

from config import DB_PATH
from data.settings_schema import (
    CATEGORY_ORDER,
    PACK_ORDER,
    RARITIES,
    SETTINGS_BY_KEY,
    SETTINGS_DEFINITIONS,
    SettingDefinition,
    defaults_map,
)

_LOCK = threading.RLock()
_CACHE: dict[str, Any] | None = None


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _decode_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _encode_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _coerce_value(defn: SettingDefinition, value: Any) -> Any:
    if defn.value_type == "bool":
        if isinstance(value, bool):
            result = value
        elif isinstance(value, (int, float)):
            result = bool(int(value))
        elif isinstance(value, str):
            low = value.strip().lower()
            if low in {"1", "true", "yes", "on"}:
                result = True
            elif low in {"0", "false", "no", "off"}:
                result = False
            else:
                raise ValueError(f"Setting {defn.key} expects boolean value")
        else:
            raise ValueError(f"Setting {defn.key} expects boolean value")
        return result

    if defn.value_type == "int":
        try:
            result = int(value)
        except Exception as exc:
            raise ValueError(f"Setting {defn.key} expects integer value") from exc
        if defn.min_value is not None and result < int(defn.min_value):
            raise ValueError(f"{defn.label} must be >= {int(defn.min_value)}")
        if defn.max_value is not None and result > int(defn.max_value):
            raise ValueError(f"{defn.label} must be <= {int(defn.max_value)}")
        return result

    if defn.value_type == "float":
        try:
            result = float(value)
        except Exception as exc:
            raise ValueError(f"Setting {defn.key} expects float value") from exc
        if defn.min_value is not None and result < float(defn.min_value):
            raise ValueError(f"{defn.label} must be >= {float(defn.min_value):g}")
        if defn.max_value is not None and result > float(defn.max_value):
            raise ValueError(f"{defn.label} must be <= {float(defn.max_value):g}")
        return result

    if defn.value_type == "str":
        result = str(value).strip()
        if not result:
            raise ValueError(f"{defn.label} cannot be empty")
        return result

    raise ValueError(f"Unsupported setting type for key {defn.key}")


def _parse_ports(raw: str) -> tuple[int, ...]:
    parts = [part.strip() for part in str(raw).split(",") if part.strip()]
    if not parts:
        raise ValueError("At least one network port is required")
    ports: list[int] = []
    for part in parts:
        try:
            port = int(part)
        except ValueError as exc:
            raise ValueError(f"Invalid port value: {part}") from exc
        if port < 1 or port > 65535:
            raise ValueError(f"Port out of range: {port}")
        if port not in ports:
            ports.append(port)
    return tuple(ports)


def _validate_cross_constraints(values: dict[str, Any]) -> None:
    deck_min = int(values["gameplay.deck_min"])
    deck_target = int(values["gameplay.deck_target"])
    deck_max = int(values["gameplay.deck_max"])
    if deck_min > deck_max:
        raise ValueError("Deck minimum cannot be greater than deck maximum")
    if deck_target < deck_min or deck_target > deck_max:
        raise ValueError("Deck target must be between deck minimum and deck maximum")

    summary_min = int(values["ai.summary_min_chars"])
    summary_max = int(values["ai.summary_max_chars"])
    if summary_min > summary_max:
        raise ValueError("Summary minimum cannot exceed summary maximum")

    _parse_ports(str(values["network.default_ports"]))

    for pack in PACK_ORDER:
        total = 0
        for rarity in RARITIES:
            weight_key = f"shop.pack.{pack}.weight.{rarity.lower()}"
            total += int(values[weight_key])
        if total <= 0:
            raise ValueError(f"{pack.title()} pack rarity weights must sum to more than zero")

    single_weights_total = sum(int(values[f"shop.single.weight.{r.lower()}"]) for r in RARITIES)
    if single_weights_total <= 0:
        raise ValueError("Single card rarity weights must sum to more than zero")


def _normalize_loaded_values(values: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(values)
    deck_min = int(normalized["gameplay.deck_min"])
    deck_max = int(normalized["gameplay.deck_max"])
    if deck_min > deck_max:
        deck_max = deck_min
        normalized["gameplay.deck_max"] = deck_max
    deck_target = int(normalized["gameplay.deck_target"])
    if deck_target < deck_min:
        normalized["gameplay.deck_target"] = deck_min
    elif deck_target > deck_max:
        normalized["gameplay.deck_target"] = deck_max

    summary_min = int(normalized["ai.summary_min_chars"])
    summary_max = int(normalized["ai.summary_max_chars"])
    if summary_min > summary_max:
        normalized["ai.summary_max_chars"] = summary_min

    # One-time migration: the legacy default of 10s for ai.request_timeout was
    # too short for cold-start remote LLMs. Bump anything <= 15 to the new
    # default of 60. Users who explicitly wanted a higher value are unaffected.
    if int(normalized.get("ai.request_timeout", 60)) <= 15:
        normalized["ai.request_timeout"] = int(SETTINGS_BY_KEY["ai.request_timeout"].default)

    try:
        _parse_ports(str(normalized["network.default_ports"]))
    except ValueError:
        normalized["network.default_ports"] = SETTINGS_BY_KEY["network.default_ports"].default

    for pack in PACK_ORDER:
        weight_keys = [f"shop.pack.{pack}.weight.{r.lower()}" for r in RARITIES]
        if sum(int(normalized[k]) for k in weight_keys) <= 0:
            normalized[f"shop.pack.{pack}.weight.common"] = 100
            for rarity in ("uncommon", "rare", "epic", "legendary"):
                normalized[f"shop.pack.{pack}.weight.{rarity}"] = 0

    if sum(int(normalized[f"shop.single.weight.{r.lower()}"]) for r in RARITIES) <= 0:
        normalized["shop.single.weight.common"] = 100
        for rarity in ("uncommon", "rare", "epic", "legendary"):
            normalized[f"shop.single.weight.{rarity}"] = 0
    return normalized


def _save_rows(conn: sqlite3.Connection, values: dict[str, Any]) -> None:
    for key, value in values.items():
        conn.execute(
            """
            INSERT INTO app_settings (key, value_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, _encode_value(value)),
        )


def _load_values_from_db() -> dict[str, Any]:
    defaults = defaults_map()
    with _connect() as conn:
        _ensure_table(conn)
        rows = conn.execute("SELECT key, value_json FROM app_settings").fetchall()
        raw_map = {str(row["key"]): str(row["value_json"]) for row in rows}

        values: dict[str, Any] = {}
        writes: dict[str, Any] = {}
        for defn in SETTINGS_DEFINITIONS:
            raw = raw_map.get(defn.key)
            if raw is None:
                values[defn.key] = defaults[defn.key]
                writes[defn.key] = defaults[defn.key]
                continue
            parsed = _decode_value(raw)
            try:
                values[defn.key] = _coerce_value(defn, parsed)
            except ValueError:
                values[defn.key] = defaults[defn.key]
                writes[defn.key] = defaults[defn.key]

        normalized = _normalize_loaded_values(values)
        for key, value in normalized.items():
            if values.get(key) != value:
                writes[key] = value

        if writes:
            _save_rows(conn, writes)
            conn.commit()
        return normalized


def ensure_loaded() -> dict[str, Any]:
    global _CACHE
    with _LOCK:
        if _CACHE is None:
            _CACHE = _load_values_from_db()
        return dict(_CACHE)


def reload_settings() -> dict[str, Any]:
    global _CACHE
    with _LOCK:
        _CACHE = _load_values_from_db()
        return dict(_CACHE)


def get_all_values() -> dict[str, Any]:
    return ensure_loaded()


def get_value(key: str) -> Any:
    if key not in SETTINGS_BY_KEY:
        raise KeyError(f"Unknown setting key: {key}")
    return ensure_loaded()[key]


def get_bool(key: str) -> bool:
    return bool(get_value(key))


def get_int(key: str) -> int:
    return int(get_value(key))


def get_float(key: str) -> float:
    return float(get_value(key))


def get_str(key: str) -> str:
    return str(get_value(key))


def set_value(key: str, value: Any) -> Any:
    if key not in SETTINGS_BY_KEY:
        raise KeyError(f"Unknown setting key: {key}")
    defn = SETTINGS_BY_KEY[key]
    coerced = _coerce_value(defn, value)

    with _LOCK:
        current = ensure_loaded()
        next_values = dict(current)
        next_values[key] = coerced
        _validate_cross_constraints(next_values)
        with _connect() as conn:
            _ensure_table(conn)
            _save_rows(conn, {key: coerced})
            conn.commit()
        global _CACHE
        _CACHE = next_values
    return coerced


def set_values(updates: dict[str, Any]) -> dict[str, Any]:
    if not updates:
        return ensure_loaded()
    with _LOCK:
        current = ensure_loaded()
        next_values = dict(current)
        normalized_updates: dict[str, Any] = {}
        for key, value in updates.items():
            if key not in SETTINGS_BY_KEY:
                raise KeyError(f"Unknown setting key: {key}")
            normalized_updates[key] = _coerce_value(SETTINGS_BY_KEY[key], value)
            next_values[key] = normalized_updates[key]
        _validate_cross_constraints(next_values)
        with _connect() as conn:
            _ensure_table(conn)
            _save_rows(conn, normalized_updates)
            conn.commit()
        global _CACHE
        _CACHE = next_values
        return dict(_CACHE)


def reset_to_defaults() -> dict[str, Any]:
    defaults = defaults_map()
    with _LOCK:
        _validate_cross_constraints(defaults)
        with _connect() as conn:
            _ensure_table(conn)
            _save_rows(conn, defaults)
            conn.commit()
        global _CACHE
        _CACHE = dict(defaults)
        return dict(_CACHE)


def reset_category(category: str) -> dict[str, Any]:
    with _LOCK:
        current = ensure_loaded()
        next_values = dict(current)
        updates: dict[str, Any] = {}
        for defn in SETTINGS_DEFINITIONS:
            if defn.category != category:
                continue
            next_values[defn.key] = defn.default
            updates[defn.key] = defn.default
        _validate_cross_constraints(next_values)
        with _connect() as conn:
            _ensure_table(conn)
            _save_rows(conn, updates)
            conn.commit()
        global _CACHE
        _CACHE = next_values
        return dict(_CACHE)


def categories() -> tuple[str, ...]:
    return CATEGORY_ORDER


def definitions_by_category() -> dict[str, list[SettingDefinition]]:
    grouped: dict[str, list[SettingDefinition]] = {name: [] for name in CATEGORY_ORDER}
    for defn in SETTINGS_DEFINITIONS:
        grouped.setdefault(defn.category, []).append(defn)
    return grouped


def target_fps() -> int:
    return get_int("display.target_fps")


def network_ports() -> tuple[int, ...]:
    return _parse_ports(get_str("network.default_ports"))
