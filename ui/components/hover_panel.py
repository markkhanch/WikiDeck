"""Hover tooltip — full Wikipedia text for the card the mouse is over.

Renders a side panel (right edge of the screen) with:
 - title, theme, rarity badges
 - short description (one-line subtitle from the Wikipedia summary)
 - extract (the first ~500 chars), wrapped to panel width
 - any ON_PLAY / ON_DEATH effects

Kept as a stateless draw-function — the owner decides when to call it based
on mouse position and visibility rules (e.g. hide the opponent's hand).
"""
import re
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
from core.card import ARCHETYPE_COLORS, Card
from core.effects import Effect, EFFECT_LABEL
from ui.effects import draw_drop_shadow, draw_glow


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
    "HP",
    "CARDS", "HAND", "FIELD", "DISCARD PILE",
    "DAMAGE", "HEAL", "DRAW", "DISCARD",
    "DESTROY", "BANISH", "REVIVE", "DUEL", "CLASH",
    "BLEEDING", "VITALITY", "POISON", "SHIELD", "IMMUNITY", "LOCK", "VEIL",
]


def _ability_terms(card: Card) -> List[str]:
    visible_sources: list[str] = []

    trigger = str(card.ability_trigger or "").strip().upper()
    ability_text = str(card.ability_text or "").strip()
    if ability_text:
        prefix = f"{trigger}: " if trigger else ""
        visible_sources.append(f"{prefix}{ability_text}")
    else:
        for label, effect in (("DEPLOY", card.on_play), ("DEATHWISH", card.on_death)):
            if effect in (None, Effect.NONE):
                continue
            pretty = str(EFFECT_LABEL.get(effect, getattr(effect, "value", str(effect))))
            visible_sources.append(f"{label}: {pretty}")

    raw_statuses = getattr(card, "statuses", {}) or {}
    if isinstance(raw_statuses, dict):
        status_tokens: list[str] = []
        for name in sorted(raw_statuses):
            value = raw_statuses[name]
            if isinstance(value, bool):
                if value:
                    status_tokens.append(str(name))
            else:
                count = int(value)
                status_tokens.append(f"{name}:{count}" if count > 1 else str(name))
    else:
        status_tokens = sorted(str(s) for s in raw_statuses)
    if getattr(card, "silenced_turns", 0) > 0:
        status_tokens.append("SILENCED")
    if status_tokens:
        visible_sources.append(" ".join(status_tokens))

    text = " ".join(visible_sources).lower().strip()
    if not text:
        return []
    terms = set()
    if re.search(r"\bdeploy\b", text):
        terms.add("DEPLOY")
    if re.search(r"\bdeathwish\b", text):
        terms.add("DEATHWISH")
    if re.search(r"\border\b", text):
        terms.add("ORDER")
    if re.search(r"\bability\b", text):
        terms.add("ABILITY")
    if re.search(r"\bhp\b", text):
        terms.add("HP")
    if re.search(r"\bcards\b", text):
        terms.add("CARDS")
    if re.search(r"\bhand\b", text):
        terms.add("HAND")
    if re.search(r"\bfield\b", text):
        terms.add("FIELD")
    if re.search(r"\bdiscard pile\b", text):
        terms.add("DISCARD PILE")
    if re.search(r"\bdamage\b", text) or re.search(r"\bdeal\b", text):
        terms.add("DAMAGE")
    if re.search(r"\bheal\b", text) or re.search(r"\brestore\b", text):
        terms.add("HEAL")
    if re.search(r"\bdraw\b", text):
        terms.add("DRAW")
    if re.search(r"\bdiscard\b", text):
        terms.add("DISCARD")
    if re.search(r"\bdestroy\b", text):
        terms.add("DESTROY")
    if re.search(r"\bbanish\b", text):
        terms.add("BANISH")
    if re.search(r"\breturn\b", text) and (re.search(r"\bdiscard\b", text) or re.search(r"\bfield\b", text)):
        terms.add("REVIVE")
    if re.search(r"\bbleeding\b", text):
        terms.add("BLEEDING")
    if re.search(r"\bvitality\b", text):
        terms.add("VITALITY")
    if re.search(r"\bpoison\b", text):
        terms.add("POISON")
    if re.search(r"\bshield\b", text):
        terms.add("SHIELD")
    if re.search(r"\bimmunity\b", text):
        terms.add("IMMUNITY")
    if re.search(r"\block\b", text):
        terms.add("LOCK")
    if re.search(r"\bveil\b", text):
        terms.add("VEIL")
    if re.search(r"\bduel\b", text):
        terms.add("DUEL")
    if re.search(r"\bclash\b", text):
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
    draw_drop_shadow(screen, panel, offset=(4, 4), size=8, alpha=140)
    draw_glow(screen, panel, NEON_BLUE, glow_size=5, alpha=120)
    pygame.draw.rect(screen, BG_DARK, panel)
    pygame.draw.rect(screen, NEON_BLUE, panel, width=2)

    # Set clip region to prevent text bleeding outside panel
    old_clip = screen.get_clip()
    clip_rect = pygame.Rect(panel.x + 2, panel.y + 2, panel.width - 4, panel.height - 4)
    screen.set_clip(clip_rect)

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

    # Badges: theme + rarity + HP
    badge_font = fonts["small"]
    theme_color = THEME_COLORS.get(card.theme, MUTED_TEXT)
    rarity_color = RARITY_COLORS.get(card.rarity, MUTED_TEXT)

    bx = cx
    badges: list[tuple[str, tuple[int, int, int]]] = [
        (card.theme, theme_color),
        (card.rarity, rarity_color),
        (f"HP {card.hp}", NEON_GREEN),
    ]
    archetype = (card.archetype or "").upper()
    if archetype in ARCHETYPE_COLORS:
        badges.append((archetype, ARCHETYPE_COLORS[archetype]))
    for text, color in badges:
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
        cy += 4

    # Rationale — biographical flavor line, italic.
    rationale = (card.rationale or "").strip()
    if rationale:
        flavor_font = pygame.font.SysFont("arial", 13, italic=True)
        for line in _wrap(f'"{rationale}"', flavor_font, text_w):
            surf = flavor_font.render(line, True, MUTED_TEXT)
            screen.blit(surf, (cx, cy))
            cy += surf.get_height() + 1
        cy += 6

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

    # Restore original clip region
    screen.set_clip(old_clip)
