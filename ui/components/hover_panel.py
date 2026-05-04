"""Hover tooltip — full Wikipedia text for the card the mouse is over.

Renders a side panel (right edge of the screen) with:
 - title, theme, rarity badges
 - short description (one-line subtitle from the Wikipedia summary)
 - extract (the first ~500 chars), wrapped to panel width
 - any ON_PLAY / ON_DEATH effects

Kept as a stateless draw-function — the owner decides when to call it based
on mouse position and visibility rules (e.g. hide the opponent's hand).
"""
from typing import List

import pygame

from config import (
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    BG_DARK,
    BG_MID,
    NEON_BLUE,
    NEON_GREEN,
    WHITE_TEXT,
    MUTED_TEXT,
    GOLD,
    THEME_COLORS,
    RARITY_COLORS,
)
from core.card import Card
from core.effects import Effect, EFFECT_LABEL


PANEL_W = 320
PANEL_H = 420
PAD = 14
GLOSSARY_W = 260


def _wrap(text: str, font: pygame.font.Font, max_w: int) -> List[str]:
    """Greedy word-wrap. Respects existing newlines."""
    lines: List[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split(" ")
        line = ""
        for w in words:
            probe = w if not line else f"{line} {w}"
            if font.size(probe)[0] <= max_w:
                line = probe
            else:
                if line:
                    lines.append(line)
                line = w
        lines.append(line)
    return lines


TERM_GLOSSARY = {
    "DEPLOY": "DEPLOY triggers activate immediately when the card is played.",
    "DEATHWISH": "DEATHWISH triggers activate when this card is defeated.",
    "ORDER": "ORDER can be activated manually once per turn.",
    "ABILITY": "Ability is the special card action text linked to trigger and effect.",
    "HP": "In card games, HP is a card's health. When it reaches 0, the card is defeated.",
    "SCORE": "Score (SC) is the card's points contribution while on the field.",
    "CARDS": "Cards are units in your hand, deck, field, or discard pile.",
    "HAND": "Hand is the set of cards you can currently play.",
    "FIELD": "Field is where active cards stay and apply effects.",
    "DISCARD PILE": "Discard pile stores used or defeated cards.",
    "DAMAGE": "Damage reduces a card's HP immediately.",
    "HEAL": "Heal restores HP, up to the card's maximum.",
    "DRAW": "Draw means taking cards from your deck into your hand.",
    "DISCARD": "Discard moves cards from your hand to your discard pile.",
    "GOLD": "Gold is a resource used for purchases or effects.",
    "DESTROY": "Destroy removes an enemy card from the battlefield.",
    "BANISH": "Banish removes a card from the game without sending it to discard.",
    "BOOST": "Boost increases a card's base score.",
    "DRAIN": "Drain lowers enemy score and transfers that amount to the source card.",
    "REVIVE": "Revive returns a defeated card to the field.",
    "BLEEDING": "BLEEDING deals 1 damage at end of turn and loses one stack.",
    "VITALITY": "VITALITY heals 1 HP at end of turn and loses one stack.",
    "POISON": "At 2 stacks, POISON destroys the unit.",
    "SHIELD": "SHIELD is a protective status that blocks or reduces damage.",
    "IMMUNITY": "IMMUNITY prevents negative effects for a short time.",
    "LOCK": "LOCK disables a card's ability.",
    "VEIL": "VEIL prevents targeting by abilities.",
    "CLASH": "CLASH makes both cards damage each other simultaneously.",
    "DUEL": "DUEL makes two cards damage each other alternately.",
}

TERM_ORDER = [
    "DEPLOY", "DEATHWISH", "ORDER", "ABILITY",
    "HP", "SCORE",
    "CARDS", "HAND", "FIELD", "DISCARD PILE",
    "DAMAGE", "BOOST", "HEAL", "DRAIN", "DRAW", "DISCARD", "GOLD",
    "DESTROY", "BANISH", "REVIVE", "DUEL", "CLASH",
    "BLEEDING", "VITALITY", "POISON", "SHIELD", "IMMUNITY", "LOCK", "VEIL",
]


def _ability_terms(card: Card) -> List[str]:
    sources = [card.ability_text or "", card.ability_trigger or ""]
    if getattr(card, "statuses", None):
        sources.append(" ".join(sorted(card.statuses)))
    if getattr(card, "silenced_turns", 0) > 0:
        sources.append("silenced")
    if card.on_play not in (None, Effect.NONE):
        sources.append("DEPLOY")
        sources.append(str(EFFECT_LABEL.get(card.on_play, getattr(card.on_play, "value", ""))))
    if card.on_death not in (None, Effect.NONE):
        sources.append("DEATHWISH")
        sources.append(str(EFFECT_LABEL.get(card.on_death, getattr(card.on_death, "value", ""))))
    text = " ".join(sources).lower().strip()
    if not text:
        return []
    terms = set()
    if "deploy" in text:
        terms.add("DEPLOY")
    if "deathwish" in text:
        terms.add("DEATHWISH")
    if "order" in text:
        terms.add("ORDER")
    if "ability" in text:
        terms.add("ABILITY")
    if "hp" in text:
        terms.add("HP")
    if "score" in text or " sc " in f" {text} ":
        terms.add("SCORE")
    if "card" in text:
        terms.add("CARDS")
    if "hand" in text:
        terms.add("HAND")
    if "field" in text:
        terms.add("FIELD")
    if "discard pile" in text:
        terms.add("DISCARD PILE")
    if "damage" in text or "deal " in text:
        terms.add("DAMAGE")
    if "heal" in text or "restore" in text:
        terms.add("HEAL")
    if "draw" in text:
        terms.add("DRAW")
    if "discard" in text:
        terms.add("DISCARD")
    if "gold" in text:
        terms.add("GOLD")
    if "destroy" in text:
        terms.add("DESTROY")
    if "banish" in text:
        terms.add("BANISH")
    if "boost" in text:
        terms.add("BOOST")
    if "drain" in text:
        terms.add("DRAIN")
    if "return" in text and ("discard" in text or "field" in text):
        terms.add("REVIVE")
    if "bleeding" in text:
        terms.add("BLEEDING")
    if "vitality" in text:
        terms.add("VITALITY")
    if "poison" in text:
        terms.add("POISON")
    if "shield" in text:
        terms.add("SHIELD")
    if "immunity" in text:
        terms.add("IMMUNITY")
    if "lock" in text:
        terms.add("LOCK")
    if "veil" in text:
        terms.add("VEIL")
    if "duel" in text:
        terms.add("DUEL")
    if "clash" in text:
        terms.add("CLASH")
    return [term for term in TERM_ORDER if term in terms]


def _draw_glossary_panel(
    screen: pygame.Surface,
    fonts: dict,
    panel: pygame.Rect,
    terms: List[str],
) -> None:
    if not terms:
        return
    body_font = fonts["small"]
    title_font = fonts.get("panel_title") or fonts["med"]
    max_w = GLOSSARY_W - PAD * 2
    title_h = title_font.get_height()
    line_h = body_font.get_height() + 1
    height = PAD * 2 + title_h + 6
    entries = []
    for term in terms:
        desc = TERM_GLOSSARY.get(term, "")
        if not desc:
            continue
        lines = _wrap(desc, body_font, max_w)
        entries.append((term, lines))
        height += line_h + len(lines) * line_h + 6

    height = min(height, SCREEN_HEIGHT - 16)
    gx = panel.right + 12
    if gx + GLOSSARY_W > SCREEN_WIDTH - 8:
        gx = panel.left - 12 - GLOSSARY_W
    gx = max(8, min(gx, SCREEN_WIDTH - GLOSSARY_W - 8))
    gy = panel.y
    if gy + height > SCREEN_HEIGHT - 8:
        gy = SCREEN_HEIGHT - height - 8
    glossary = pygame.Rect(gx, gy, GLOSSARY_W, height)
    pygame.draw.rect(screen, BG_DARK, glossary)
    pygame.draw.rect(screen, NEON_BLUE, glossary, width=2)

    cx = glossary.x + PAD
    cy = glossary.y + PAD
    title = title_font.render("Glossary", True, WHITE_TEXT)
    screen.blit(title, (cx, cy))
    cy += title_h + 6

    for term, lines in entries:
        if cy + line_h > glossary.bottom - PAD:
            break
        term_surf = body_font.render(f"{term}:", True, GOLD)
        screen.blit(term_surf, (cx, cy))
        cy += line_h
        for line in lines:
            if cy + line_h > glossary.bottom - PAD:
                break
            surf = body_font.render(line, True, MUTED_TEXT)
            screen.blit(surf, (cx, cy))
            cy += line_h
        cy += 4


def _text_color_for(bg: tuple[int, int, int]) -> tuple[int, int, int]:
    luminance = 0.2126 * bg[0] + 0.7152 * bg[1] + 0.0722 * bg[2]
    return BG_DARK if luminance > 165 else WHITE_TEXT


def _draw_badge(
    screen: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    color: tuple[int, int, int],
    pos: tuple[int, int],
) -> tuple[int, int]:
    text_color = _text_color_for(color)
    pad = 4
    surf = font.render(text, True, text_color)
    badge = pygame.Rect(pos[0], pos[1], surf.get_width() + pad * 2, surf.get_height() + 2)
    pygame.draw.rect(screen, color, badge)
    shadow = BG_DARK if text_color == WHITE_TEXT else WHITE_TEXT
    shadow_surf = font.render(text, True, shadow)
    screen.blit(shadow_surf, (badge.x + pad + 1, badge.y + 2))
    screen.blit(surf, (badge.x + pad, badge.y + 1))
    return badge.width, badge.height


def draw_hover_panel(
    screen: pygame.Surface,
    card: Card,
    fonts: dict,
    anchor: pygame.FRect,
) -> None:
    """Draw the panel near `anchor` but clamped inside the screen."""
    # Prefer right of the card; flip to left if it would go off-screen.
    px = anchor.right + 12
    if px + PANEL_W > SCREEN_WIDTH - 8:
        px = anchor.left - 12 - PANEL_W
    px = max(8, min(px, SCREEN_WIDTH - PANEL_W - 8))
    py = max(8, min(int(anchor.centery - PANEL_H // 2), SCREEN_HEIGHT - PANEL_H - 8))

    panel = pygame.Rect(px, py, PANEL_W, PANEL_H)
    pygame.draw.rect(screen, BG_DARK, panel)
    pygame.draw.rect(screen, NEON_BLUE, panel, width=2)

    cx = panel.x + PAD
    cy = panel.y + PAD
    text_w = PANEL_W - 2 * PAD

    # Title
    title_font = fonts.get("panel_title") or fonts["med"]
    title_lines = _wrap(card.title, title_font, text_w)
    for line in title_lines:
        surf = title_font.render(line, True, WHITE_TEXT)
        screen.blit(surf, (cx, cy))
        cy += surf.get_height() + 2
    cy += 4

    # Badges: theme + rarity + HP/SC
    badge_font = fonts["small"]
    theme_color = THEME_COLORS.get(card.theme, MUTED_TEXT)
    rarity_color = RARITY_COLORS.get(card.rarity, MUTED_TEXT)

    bx = cx
    for text, color in (
        (card.theme, theme_color),
        (card.rarity, rarity_color),
        (f"HP {card.hp}", NEON_GREEN),
        (f"SC {card.base_score}", GOLD),
    ):
        bw, bh = _draw_badge(screen, badge_font, text, color, (bx, cy))
        bx += bw + 4
        if bx + 60 > panel.right - PAD:  # wrap to next line if needed
            bx = cx
            cy += bh + 4
    cy += badge_font.get_height() + 10

    # Effects
    effect_font = fonts["small"]
    has_ability_text = bool((card.ability_text or "").strip())
    has_runtime_effect = card.on_play not in (None, Effect.NONE) or card.on_death not in (None, Effect.NONE)
    if has_ability_text:
        trigger = card.ability_trigger or "ABILITY"
        for line in _wrap(f"{trigger}:  {card.ability_text}", effect_font, text_w):
            surf = effect_font.render(line, True, GOLD)
            screen.blit(surf, (cx, cy))
            cy += surf.get_height() + 2
        if not has_runtime_effect:
            for line in _wrap("Not implemented in MVP", effect_font, text_w):
                note = effect_font.render(line, True, MUTED_TEXT)
                screen.blit(note, (cx, cy))
                cy += note.get_height() + 2

    if not has_ability_text:
        for label, eff in (("DEPLOY", card.on_play), ("DEATHWISH", card.on_death)):
            if eff in (None, Effect.NONE):
                continue
            line = f"{label}:  {EFFECT_LABEL.get(eff, getattr(eff, 'value', str(eff)))}"
            surf = effect_font.render(line, True, GOLD)
            screen.blit(surf, (cx, cy))
            cy += surf.get_height() + 2
        if has_runtime_effect:
            cy += 6

    raw_statuses = getattr(card, "statuses", {}) or {}
    if isinstance(raw_statuses, dict):
        status_list = []
        for name in sorted(raw_statuses):
            value = raw_statuses[name]
            if isinstance(value, bool):
                if value:
                    status_list.append(name)
            else:
                count = int(value)
                status_list.append(f"{name}:{count}" if count > 1 else name)
    else:
        status_list = sorted(getattr(card, "statuses", set()) or set())
    if getattr(card, "silenced_turns", 0) > 0:
        status_list.append(f"SILENCED({card.silenced_turns})")
    if status_list:
        for line in _wrap(f"Statuses: {', '.join(status_list)}", effect_font, text_w):
            surf = effect_font.render(line, True, NEON_GREEN)
            screen.blit(surf, (cx, cy))
            cy += surf.get_height() + 2
        cy += 6

    # Subtitle (one-line Wikipedia "description")
    body_font = fonts["small"]
    if card.description:
        for line in _wrap(card.description, body_font, text_w):
            surf = body_font.render(line, True, MUTED_TEXT)
            screen.blit(surf, (cx, cy))
            cy += surf.get_height() + 1
        cy += 6

    # Extract — first paragraph, clipped to what fits
    if card.extract:
        remaining = panel.bottom - PAD - cy
        max_lines = max(0, remaining // (body_font.get_height() + 1))
        for line in _wrap(card.extract, body_font, text_w)[:max_lines]:
            surf = body_font.render(line, True, WHITE_TEXT)
            screen.blit(surf, (cx, cy))
            cy += surf.get_height() + 1

    terms = _ability_terms(card)
    if terms:
        _draw_glossary_panel(screen, fonts, panel, terms)
