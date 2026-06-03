"""Install a curated demo deck — 25 cards covering every trigger and effect.

Run before a showcase so the active deck deterministically demonstrates
every mechanic. Idempotent: rerunning resets the active deck to exactly
these 25 cards.

Usage:
    python3 -m tools.demo_deck

What it does:
 1. Inserts (or replaces) 25 hand-authored card specs in the `cards` table.
 2. Adds each card to the collection (only if not already owned).
 3. Resets the active deck to these 25 cards, count = 1 each.
 4. Prefetches Wikipedia summary + image for every title.

Design constraints (no nonsense pairings):
 - DEATHWISH never grants self-defence (SHIELD/IMMUNITY/VEIL on a dead card
   is pointless). Instead: DEATHWISH carries DAMAGE / REVIVE / DRAW /
   VITALITY-to-ally (legacy lives on).
 - DEATHBLOW grants what the card "earns" from a kill: DAMAGE, DRAW.
 - ORDER carries strong active effects (DAMAGE 3, REVIVE).
 - TIMER fires an event (DESTROY), never a passive status.
 - ADRENALINE / BLOODTHIRST grant offensive or stabilizing effects only.

Trigger / effect coverage:
    DEPLOY, ORDER, DEATHWISH, DEATHBLOW, TIMER, ADRENALINE, BLOODTHIRST.
    DAMAGE, DESTROY, BANISH, HEAL, VITALITY, BLEEDING, POISON, SHIELD,
    IMMUNITY, VEIL, LOCK, DRAW, DISCARD, CLASH, REVIVE.
    (DUEL, DOOMED omitted for deck size — show on demand from BD.)

Profile: aggressive — 8 direct-damage cards, 2 destroy/banish, 3 healing,
3 vitality stacks, 3 control, plus 6 utility/draw.
"""
from __future__ import annotations

import os
import sys

# Allow running as a script: `python3 tools/demo_deck.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.db import (  # noqa: E402
    add_to_collection,
    get_active_deck_id,
    get_collection,
    get_deck_cards,
    init_db,
    prefetch_card_assets,
    save_card,
    set_deck_count,
)


DEMO_DECK: list[dict] = [
    # ───────── LEGENDARY (5) — heavy hitters and signature cards ─────────
    {
        "title": "Albert Einstein",
        "theme": "LIVING", "epoch": "MODERN", "rarity": "LEGENDARY",
        "trigger": "DEPLOY", "trigger_value": 0,
        "effect_type": "DRAW", "ability_value": 2,
        "ability_text": "Draw 2 cards.",
        "nemesis": None, "hp": 6, "base_score": 0,
        "archetype": "SCHOLAR",
        "rationale": "His thought experiments pulled the universe into clearer focus.",
    },
    {
        "title": "Napoleon",
        "theme": "LIVING", "epoch": "EARLY_MODERN", "rarity": "LEGENDARY",
        "trigger": "DEPLOY", "trigger_value": 0,
        "effect_type": "DAMAGE", "ability_value": 3,
        "ability_text": "Deal 3 damage to one enemy card.",
        "nemesis": "Duke of Wellington", "hp": 7, "base_score": 0,
        "archetype": "WARRIOR",
        "rationale": "Artillery announced his arrival before diplomats could speak.",
    },
    {
        "title": "Julius Caesar",
        "theme": "LIVING", "epoch": "ANCIENT", "rarity": "LEGENDARY",
        "trigger": "DEATHBLOW", "trigger_value": 0,
        "effect_type": "DRAW", "ability_value": 2,
        "ability_text": "Deathblow: Draw 2 cards.",
        "nemesis": "Pompey", "hp": 7, "base_score": 0,
        "archetype": "WARRIOR",
        "rationale": "Every conquered field taught him the next campaign.",
    },
    {
        "title": "Alexander the Great",
        "theme": "LIVING", "epoch": "ANCIENT", "rarity": "LEGENDARY",
        "trigger": "DEATHBLOW", "trigger_value": 0,
        "effect_type": "DAMAGE", "ability_value": 2,
        "ability_text": "Deathblow: Deal 2 damage to one enemy card.",
        "nemesis": "Darius III", "hp": 7, "base_score": 0,
        "archetype": "WARRIOR",
        "rationale": "Each conquest only sharpened his appetite for the next.",
    },
    {
        "title": "Cleopatra",
        "theme": "LIVING", "epoch": "ANCIENT", "rarity": "LEGENDARY",
        "trigger": "DEPLOY", "trigger_value": 0,
        "effect_type": "DISCARD", "ability_value": 2,
        "ability_text": "Discard 2 cards from the enemy hand.",
        "nemesis": "Augustus", "hp": 6, "base_score": 0,
        "archetype": "DIPLOMAT",
        "rationale": "She turned every audience chamber into her own theatre.",
    },

    # ───────── EPIC (6) — strong active effects ─────────
    {
        "title": "Isaac Newton",
        "theme": "LIVING", "epoch": "EARLY_MODERN", "rarity": "EPIC",
        "trigger": "ORDER", "trigger_value": 0,
        "effect_type": "DAMAGE", "ability_value": 3,
        "ability_text": "Order: Deal 3 damage to one enemy card.",
        "nemesis": "Gottfried Wilhelm Leibniz", "hp": 6, "base_score": 0,
        "archetype": "SCHOLAR",
        "rationale": "He named the force that pins every thing in its place.",
    },
    {
        "title": "Genghis Khan",
        "theme": "LIVING", "epoch": "MEDIEVAL", "rarity": "EPIC",
        "trigger": "DEPLOY", "trigger_value": 0,
        "effect_type": "DESTROY", "ability_value": 0,
        "ability_text": "Destroy one enemy card.",
        "nemesis": "Jalal ad-Din Mingburnu", "hp": 7, "base_score": 0,
        "archetype": "WARRIOR",
        "rationale": "He inherited a tent and left behind a continent of ash.",
    },
    {
        "title": "Spartacus",
        "theme": "LIVING", "epoch": "ANCIENT", "rarity": "EPIC",
        "trigger": "DEATHWISH", "trigger_value": 0,
        "effect_type": "DAMAGE", "ability_value": 2,
        "ability_text": "Deathwish: Deal 2 damage to one enemy card.",
        "nemesis": "Marcus Licinius Crassus", "hp": 6, "base_score": 0,
        "archetype": "WARRIOR",
        "rationale": "Even nailed to a cross, the rebellion still marched in his name.",
    },
    {
        "title": "Sun Tzu",
        "theme": "LIVING", "epoch": "ANCIENT", "rarity": "EPIC",
        "trigger": "DEPLOY", "trigger_value": 0,
        "effect_type": "LOCK", "ability_value": 0,
        "ability_text": "Lock an enemy card.",
        "nemesis": None, "hp": 5, "base_score": 0,
        "archetype": "SCHOLAR",
        "rationale": "He won wars before the first arrow ever left the bow.",
    },
    {
        "title": "Mahatma Gandhi",
        "theme": "LIVING", "epoch": "MODERN", "rarity": "EPIC",
        "trigger": "DEPLOY", "trigger_value": 0,
        "effect_type": "IMMUNITY", "ability_value": 0,
        "ability_text": "Give this card Immunity.",
        "nemesis": None, "hp": 5, "base_score": 0,
        "archetype": "DIPLOMAT",
        "rationale": "He stopped an empire with silence and a spinning wheel.",
    },
    {
        "title": "Augustus",
        "theme": "LIVING", "epoch": "ANCIENT", "rarity": "EPIC",
        "trigger": "DEPLOY", "trigger_value": 0,
        "effect_type": "BANISH", "ability_value": 0,
        "ability_text": "Banish one enemy card.",
        "nemesis": "Mark Antony", "hp": 6, "base_score": 0,
        "archetype": "DIPLOMAT",
        "rationale": "He erased rivals from history more thoroughly than any sword.",
    },

    # ───────── RARE (5) — variety and creative triggers ─────────
    {
        "title": "Hannibal",
        "theme": "LIVING", "epoch": "ANCIENT", "rarity": "RARE",
        "trigger": "DEPLOY", "trigger_value": 0,
        "effect_type": "CLASH", "ability_value": 0,
        "ability_text": "Clash with one enemy card.",
        "nemesis": "Scipio Africanus", "hp": 5, "base_score": 0,
        "archetype": "WARRIOR",
        "rationale": "He marched elephants across the Alps to meet Rome on its threshold.",
    },
    {
        "title": "Marie Curie",
        "theme": "LIVING", "epoch": "MODERN", "rarity": "RARE",
        "trigger": "DEPLOY", "trigger_value": 0,
        "effect_type": "POISON", "ability_value": 0,
        "ability_text": "Give an enemy card Poison.",
        "nemesis": None, "hp": 5, "base_score": 0,
        "archetype": "SCHOLAR",
        "rationale": "She held the glow that killed her, and called it discovery.",
    },
    {
        "title": "Joan of Arc",
        "theme": "LIVING", "epoch": "MEDIEVAL", "rarity": "RARE",
        "trigger": "DEATHWISH", "trigger_value": 0,
        "effect_type": "VITALITY", "ability_value": 3,
        "ability_text": "Deathwish: Give an allied card Vitality for 3 turns.",
        "nemesis": "John of Lancaster", "hp": 5, "base_score": 0,
        "archetype": "HEALER",
        "rationale": "Her ashes spoke louder than the verdict that made them.",
    },
    {
        "title": "Wolfgang Amadeus Mozart",
        "theme": "LIVING", "epoch": "EARLY_MODERN", "rarity": "RARE",
        "trigger": "DEATHWISH", "trigger_value": 0,
        "effect_type": "DRAW", "ability_value": 2,
        "ability_text": "Deathwish: Draw 2 cards.",
        "nemesis": "Antonio Salieri", "hp": 4, "base_score": 0,
        "archetype": "ARTIST",
        "rationale": "His melodies still teach the dying how to live.",
    },
    {
        "title": "Frida Kahlo",
        "theme": "LIVING", "epoch": "MODERN", "rarity": "RARE",
        "trigger": "ADRENALINE", "trigger_value": 2,
        "effect_type": "VITALITY", "ability_value": 2,
        "ability_text": "Give this card Vitality for 2 turns.",
        "nemesis": None, "hp": 5, "base_score": 0,
        "archetype": "ARTIST",
        "rationale": "She painted her own bones together when no doctor could.",
    },

    # ───────── UNCOMMON (5) — backbone effects ─────────
    {
        "title": "Florence Nightingale",
        "theme": "LIVING", "epoch": "MODERN", "rarity": "UNCOMMON",
        "trigger": "DEPLOY", "trigger_value": 0,
        "effect_type": "HEAL", "ability_value": 0,
        "ability_text": "Heal this card.",
        "nemesis": None, "hp": 4, "base_score": 0,
        "archetype": "HEALER",
        "rationale": "Her lamp turned soldier wards from waiting rooms into hospitals.",
    },
    {
        "title": "Hippocrates",
        "theme": "LIVING", "epoch": "ANCIENT", "rarity": "UNCOMMON",
        "trigger": "DEPLOY", "trigger_value": 0,
        "effect_type": "SHIELD", "ability_value": 0,
        "ability_text": "Give this card Shield.",
        "nemesis": None, "hp": 4, "base_score": 0,
        "archetype": "HEALER",
        "rationale": "He taught medicine to first promise no harm.",
    },
    {
        "title": "Vlad the Impaler",
        "theme": "LIVING", "epoch": "MEDIEVAL", "rarity": "UNCOMMON",
        "trigger": "DEPLOY", "trigger_value": 0,
        "effect_type": "BLEEDING", "ability_value": 2,
        "ability_text": "Give an enemy card Bleeding for 2 turns.",
        "nemesis": "Mehmed II", "hp": 5, "base_score": 0,
        "archetype": "TYRANT",
        "rationale": "He turned a forest of stakes into a border no army would cross.",
    },
    {
        "title": "Maximilien Robespierre",
        "theme": "LIVING", "epoch": "EARLY_MODERN", "rarity": "UNCOMMON",
        "trigger": "TIMER", "trigger_value": 2,
        "effect_type": "DESTROY", "ability_value": 0,
        "ability_text": "Timer 2: Destroy one enemy card.",
        "nemesis": "Georges Danton", "hp": 4, "base_score": 0,
        "archetype": "TYRANT",
        "rationale": "Virtue was his blade, and the Terror its edge.",
    },
    {
        "title": "Leonardo da Vinci",
        "theme": "LIVING", "epoch": "EARLY_MODERN", "rarity": "UNCOMMON",
        "trigger": "ORDER", "trigger_value": 0,
        "effect_type": "REVIVE", "ability_value": 0,
        "ability_text": "Order: Return one card from your discard pile to the field.",
        "nemesis": None, "hp": 5, "base_score": 0,
        "archetype": "ARTIST",
        "rationale": "Every sketch was a prophecy waiting for its tools.",
    },

    # ───────── COMMON (4) — cheap, splashable utility ─────────
    {
        "title": "Lucrezia Borgia",
        "theme": "LIVING", "epoch": "MEDIEVAL", "rarity": "COMMON",
        "trigger": "DEPLOY", "trigger_value": 0,
        "effect_type": "POISON", "ability_value": 0,
        "ability_text": "Give an enemy card Poison.",
        "nemesis": None, "hp": 3, "base_score": 0,
        "archetype": "TYRANT",
        "rationale": "Her dinners ended whatever business had brought a guest to the door.",
    },
    {
        "title": "Confucius",
        "theme": "LIVING", "epoch": "ANCIENT", "rarity": "COMMON",
        "trigger": "DEATHWISH", "trigger_value": 0,
        "effect_type": "REVIVE", "ability_value": 0,
        "ability_text": "Deathwish: Return one card from your discard pile to the field.",
        "nemesis": None, "hp": 3, "base_score": 0,
        "archetype": "SCHOLAR",
        "rationale": "His teachings outlasted the empires that ignored them.",
    },
    {
        "title": "Otto von Bismarck",
        "theme": "LIVING", "epoch": "EARLY_MODERN", "rarity": "COMMON",
        "trigger": "BLOODTHIRST", "trigger_value": 2,
        "effect_type": "DAMAGE", "ability_value": 2,
        "ability_text": "Deal 2 damage to one enemy card.",
        "nemesis": "Napoleon III", "hp": 4, "base_score": 0,
        "archetype": "DIPLOMAT",
        "rationale": "He stitched a country together one annexation at a time.",
    },
    {
        "title": "Niccolò Machiavelli",
        "theme": "LIVING", "epoch": "EARLY_MODERN", "rarity": "COMMON",
        "trigger": "DEPLOY", "trigger_value": 0,
        "effect_type": "VEIL", "ability_value": 0,
        "ability_text": "Give this card Veil.",
        "nemesis": None, "hp": 4, "base_score": 0,
        "archetype": "SCHOLAR",
        "rationale": "He told princes the truth they already knew but never spoke.",
    },
]


def install_demo_deck() -> None:
    init_db()
    deck_id = get_active_deck_id()

    # 1) Clear current active deck so the result is exactly DEMO_DECK.
    cleared = 0
    for entry in list(get_deck_cards(deck_id)):
        set_deck_count(entry["title"], entry["rarity"], 0, deck_id=deck_id)
        cleared += 1
    if cleared:
        print(f"Cleared {cleared} cards from active deck.")

    # 2) Snapshot collection so rerunning doesn't grant a 2nd, 3rd, ... copy.
    owned = {(e["title"], e["rarity"]): int(e["count"])
             for e in get_collection()}

    print(f"\nInstalling {len(DEMO_DECK)} demo cards into active deck:")
    print(f"  {'#':>2}  {'TITLE':30}  {'RARITY':10}  {'TRIGGER':>11} → {'EFFECT':10}  HP")
    print(f"  {'──':>2}  {'─' * 30}  {'─' * 10}  {'─' * 11}   {'─' * 10}  ──")

    for idx, spec in enumerate(DEMO_DECK, start=1):
        save_card(spec)
        if owned.get((spec["title"], spec["rarity"]), 0) == 0:
            add_to_collection(spec["title"], spec["rarity"], 1)
        set_deck_count(spec["title"], spec["rarity"], 1, deck_id=deck_id)

        print(
            f"  {idx:>2}  {spec['title']:30}  {spec['rarity']:10}  "
            f"{spec['trigger']:>11} → {spec['effect_type']:10}  {spec['hp']}"
        )

        try:
            prefetch_card_assets(spec["title"])
        except Exception as exc:
            print(f"      ! image fetch failed: {exc}")

    print(f"\n✅ Demo deck ready. Active deck now has exactly {len(DEMO_DECK)} cards.")
    print("Launch the game → PLAY → Quick Match. You're showcase-ready.")


if __name__ == "__main__":
    install_demo_deck()
