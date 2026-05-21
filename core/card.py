"""Card dataclass — the atomic unit of WikiDeck.

MVP version: on_play / on_death triggers (see core/effects.py), no epoch /
nemesis / statuses yet. Enough to render a Wikipedia article on screen and
carry a tiny bit of behaviour.
"""
from dataclasses import dataclass, field
from typing import Optional

import pygame

from config import CARD_WIDTH, CARD_HEIGHT, BG_DARK, BG_LIGHT, WHITE_TEXT, NEON_RED, GOLD, THEME_COLORS, RARITY_COLORS
from core.effects import Effect
from ui.effects import draw_drop_shadow, draw_glow


def _draw_text_with_shadow(
    surface: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    color: tuple[int, int, int],
    pos: tuple[int, int],
) -> None:
    shadow = BG_DARK if color == WHITE_TEXT else WHITE_TEXT
    shadow_surf = font.render(text, True, shadow)
    surface.blit(shadow_surf, (pos[0] + 1, pos[1] + 1))
    text_surf = font.render(text, True, color)
    surface.blit(text_surf, pos)


def _darken(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))


def _blit_cover(surface: pygame.Surface, image: pygame.Surface, rect: pygame.Rect) -> None:
    """Scale image to cover rect while preserving aspect ratio (center-crop)."""
    iw, ih = image.get_size()
    if iw <= 0 or ih <= 0:
        return
    scale = max(rect.width / iw, rect.height / ih)
    new_w = max(1, int(iw * scale))
    new_h = max(1, int(ih * scale))
    scaled = pygame.transform.smoothscale(image, (new_w, new_h))
    dx = (rect.width - new_w) // 2
    dy = (rect.height - new_h) // 2
    temp = pygame.Surface(rect.size, pygame.SRCALPHA)
    temp.blit(scaled, (dx, dy))
    surface.blit(temp, rect.topleft)


def _blit_contain(
    surface: pygame.Surface,
    image: pygame.Surface,
    rect: pygame.Rect,
    fill: tuple[int, int, int],
) -> None:
    iw, ih = image.get_size()
    if iw <= 0 or ih <= 0:
        return
    scale = min(rect.width / iw, rect.height / ih)
    new_w = max(1, int(iw * scale))
    new_h = max(1, int(ih * scale))
    scaled = pygame.transform.smoothscale(image, (new_w, new_h))
    dx = (rect.width - new_w) // 2
    dy = (rect.height - new_h) // 2
    temp = pygame.Surface(rect.size, pygame.SRCALPHA)
    temp.fill(fill)
    temp.blit(scaled, (dx, dy))
    surface.blit(temp, rect.topleft)


@dataclass
class Card:
    title: str
    hp: int = 3
    theme: str = "CONCEPTS"
    rarity: str = "COMMON"
    epoch: str = "TIMELESS"
    nemesis: Optional[str] = None
    description: str = ""   # short Wikipedia subtitle (~1 line)
    extract: str = ""       # first paragraph of the article (~500 chars)
    image: Optional[pygame.Surface] = None
    ability_text: str = ""  # AI-authored ability description (optional)
    ability_trigger: str = ""  # Raw trigger label from generator (optional)
    trigger_value: int = 0
    effect_type: str = "NONE"
    ability_value: int = 0
    max_hp: int = 0
    graveyard_eligible: bool = False
    statuses: dict[str, int | bool] = field(default_factory=dict)
    silenced_turns: int = 0
    on_play:  Effect = Effect.NONE
    on_death: Effect = Effect.NONE
    # Position + hitbox on screen. FRect for smooth sub-pixel drag.
    rect: pygame.FRect = field(
        default_factory=lambda: pygame.FRect(0, 0, CARD_WIDTH, CARD_HEIGHT)
    )

    def __post_init__(self) -> None:
        if self.max_hp <= 0:
            self.max_hp = max(1, int(self.hp))
        if isinstance(self.statuses, list):
            self.statuses = {str(name).upper(): 1 for name in self.statuses}
        elif isinstance(self.statuses, set):
            self.statuses = {str(name).upper(): 1 for name in self.statuses}
        elif isinstance(self.statuses, dict):
            normalized: dict[str, int | bool] = {}
            for raw_name, raw_value in self.statuses.items():
                name = str(raw_name).upper()
                if isinstance(raw_value, bool):
                    if raw_value:
                        normalized[name] = True
                else:
                    try:
                        value = int(raw_value)
                    except Exception:
                        value = 1
                    if value > 0:
                        normalized[name] = value
            self.statuses = normalized
        else:
            self.statuses = {}
        if isinstance(self.nemesis, str):
            trimmed = self.nemesis.strip()
            self.nemesis = trimmed or None

    # ---- placement helpers ----
    def set_center(self, x: float, y: float) -> None:
        self.rect.center = (x, y)

    def set_topleft(self, x: float, y: float) -> None:
        self.rect.topleft = (x, y)

    # ---- rendering ----
    def draw(self, surface: pygame.Surface) -> None:
        """Render this card with full-bleed art and compact overlays."""
        theme_color  = THEME_COLORS.get(self.theme, WHITE_TEXT)
        border_color = RARITY_COLORS.get(self.rarity, WHITE_TEXT)
        x, y = int(self.rect.x), int(self.rect.y)
        frame = pygame.Rect(x, y, CARD_WIDTH, CARD_HEIGHT)
        inner = frame.inflate(-4, -4)

        draw_drop_shadow(surface, frame, offset=(3, 3), size=6, alpha=100)
        draw_glow(surface, frame, border_color, glow_size=6, alpha=140)

        pygame.draw.rect(surface, BG_LIGHT, frame, border_radius=8)
        pygame.draw.rect(surface, border_color, frame, width=2, border_radius=8)

        # Full-card artwork (no cropped strip).
        if self.image is not None:
            iw, ih = self.image.get_size()
            rect_ratio = inner.width / max(1, inner.height)
            img_ratio = iw / ih if ih else rect_ratio
            if img_ratio > rect_ratio * 1.9 or img_ratio < rect_ratio * 0.55:
                _blit_contain(surface, self.image, inner, _darken(theme_color, 0.4))
            else:
                _blit_cover(surface, self.image, inner)
        else:
            pygame.draw.rect(surface, _darken(theme_color, 0.6), inner)
            initial = (self.title[:1] or "?").upper()
            font_initial = pygame.font.SysFont("arial", 34, bold=True)
            ini_surf = font_initial.render(initial, True, WHITE_TEXT)
            surface.blit(ini_surf, ini_surf.get_rect(center=inner.center))

        # Readability overlays.
        tint = pygame.Surface(inner.size, pygame.SRCALPHA)
        tint.fill((0, 0, 0, 54))
        surface.blit(tint, inner.topleft)
        top_band_h = 26
        bottom_band_h = 34
        top_band = pygame.Surface((inner.width, top_band_h), pygame.SRCALPHA)
        top_band.fill((0, 0, 0, 170))
        surface.blit(top_band, (inner.x, inner.y))
        bottom_band = pygame.Surface((inner.width, bottom_band_h), pygame.SRCALPHA)
        bottom_band.fill((0, 0, 0, 190))
        surface.blit(bottom_band, (inner.x, inner.bottom - bottom_band_h))

        # Title on bottom band.
        font_title = pygame.font.SysFont("arial", 11, bold=True)
        _draw_text_with_shadow(surface, font_title, self.title[:18], WHITE_TEXT, (inner.x + 4, inner.bottom - 24))

        # HP top-left.
        font_stat = pygame.font.SysFont("arial", 10, bold=True)
        hp_rect = pygame.Rect(inner.x + 4, inner.y + 4, 40, 18)
        pygame.draw.rect(surface, BG_DARK, hp_rect)
        pygame.draw.rect(surface, NEON_RED, hp_rect, width=1)
        hp_surf = font_stat.render(f"HP{self.hp}", True, NEON_RED)
        surface.blit(hp_surf, hp_surf.get_rect(center=hp_rect.center))

        # Status strip above title if statuses are active.
        status_labels: list[str] = []
        for name in sorted(self.statuses):
            value = self.statuses[name]
            if isinstance(value, bool):
                if value:
                    status_labels.append(name)
                continue
            if int(value) > 1:
                status_labels.append(f"{name}:{int(value)}")
            elif int(value) == 1:
                status_labels.append(name)
        if self.silenced_turns > 0:
            status_labels.append(f"SIL:{self.silenced_turns}")
        if status_labels:
            badge_font = pygame.font.SysFont("arial", 9, bold=True)
            display = ", ".join(status_labels[:2])
            if len(status_labels) > 2:
                display += f" +{len(status_labels) - 2}"
            badge_rect = pygame.Rect(inner.x + 4, inner.bottom - bottom_band_h - 11, inner.width - 8, 10)
            pygame.draw.rect(surface, BG_DARK, badge_rect)
            pygame.draw.rect(surface, GOLD, badge_rect, width=1)
            status_surf = badge_font.render(display, True, GOLD)
            surface.blit(status_surf, (badge_rect.x + 2, badge_rect.y))
