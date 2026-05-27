"""Print balance distribution of the saved card database.

Usage:
    python3 -m tools.balance_report

Shows actual vs target shares for effects, triggers, and archetypes.
Bar markers make it easy to spot over- and under-represented categories.
"""
from __future__ import annotations

import os
import sys

# Allow running as a script: `python3 tools/balance_report.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.db import (  # noqa: E402
    get_archetype_distribution,
    get_effect_distribution,
    get_trigger_distribution,
    init_db,
)
from data.ollama_gen_v2 import (  # noqa: E402
    ARCHETYPES,
    EFFECT_TARGET_SHARE,
    TRIGGER_TARGET_SHARE,
)

BAR_WIDTH = 30


def _bar(actual_pct: float, target_pct: float, width: int = BAR_WIDTH) -> str:
    a_fill = min(width, int(round(actual_pct / 100 * width)))
    t_pos = min(width - 1, int(round(target_pct / 100 * width)))
    cells = ["·"] * width
    for i in range(a_fill):
        cells[i] = "█"
    # target marker (overrides if inside bar; appears on top of fill)
    if 0 <= t_pos < width:
        cells[t_pos] = "|"
    return "".join(cells)


def _print_table(
    title: str,
    distribution: dict[str, int],
    targets: dict[str, float],
) -> None:
    total = sum(distribution.values()) or 1
    print(f"\n=== {title} ({total} entries) ===")
    print(f"  {'KEY':18}  {'COUNT':>5}  {'ACTUAL':>7}  {'TARGET':>7}  CHART (target=|)")
    keys = sorted(set(distribution) | set(targets))
    for key in keys:
        count = distribution.get(key, 0)
        actual_share = count / total
        target_share = targets.get(key, 0.0)
        delta = actual_share - target_share
        flag = ""
        if abs(delta) >= 0.05:
            flag = "OVER" if delta > 0 else "UNDER"
        elif abs(delta) >= 0.025:
            flag = "."
        bar = _bar(actual_share * 100, target_share * 100)
        print(
            f"  {key:18}  {count:5d}  {actual_share*100:6.1f}%  {target_share*100:6.1f}%  {bar}  {flag}"
        )


def _print_archetype_table(distribution: dict[str, int]) -> None:
    total = sum(distribution.values()) or 1
    print(f"\n=== ARCHETYPES ({total} entries) ===")
    target_share = 1.0 / max(1, len(ARCHETYPES))  # uniform target
    print(f"  {'KEY':18}  {'COUNT':>5}  {'ACTUAL':>7}  {'TARGET':>7}  CHART")
    for arch in sorted(ARCHETYPES):
        count = distribution.get(arch, 0)
        actual_share = count / total
        delta = actual_share - target_share
        flag = "OVER" if delta > 0.05 else ("UNDER" if delta < -0.05 else "")
        bar = _bar(actual_share * 100, target_share * 100)
        print(
            f"  {arch:18}  {count:5d}  {actual_share*100:6.1f}%  {target_share*100:6.1f}%  {bar}  {flag}"
        )
    # Old cards without archetype field surface as "" here.
    missing = distribution.get("", 0)
    if missing:
        print(f"  {'(missing)':18}  {missing:5d}    -- legacy cards without archetype")


def main() -> None:
    init_db()
    effects = get_effect_distribution()
    triggers = get_trigger_distribution()
    archetypes = get_archetype_distribution()

    _print_table("EFFECTS", effects, EFFECT_TARGET_SHARE)
    _print_table("TRIGGERS", triggers, TRIGGER_TARGET_SHARE)
    _print_archetype_table(archetypes)

    total_cards = sum(effects.values())
    print(
        f"\nTotal cards in DB: {total_cards}.  "
        f"Global balancer is {'active' if total_cards >= 30 else 'still warming up (needs 30+)'}."
    )


if __name__ == "__main__":
    main()
