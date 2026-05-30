"""Card dataclass — the atomic unit of WikiDeck.

MVP version: on_play / on_death triggers (see core/effects.py), no epoch /
nemesis / statuses yet. Enough to render a Wikipedia article on screen and
carry a tiny bit of behaviour.
"""
from dataclasses import dataclass, field
from typing import Optional

import pygame

from config import CARD_WIDTH, CARD_HEIGHT, BG_DARK, BG_LIGHT, WHITE_TEXT, NEON_RED, GOLD, NEON_GREEN, THEME_COLORS, RARITY_COLORS
from core.effects import Effect
from core.icons import SUPPORTED_STATUSES, get_status_icon, get_trigger_icon
from ui.effects import draw_drop_shadow, draw_glow


ARCHETYPE_COLORS: dict[str, tuple[int, int, int]] = {
    "WARRIOR":  (220,  80,  80),   # red
    "TYRANT":   (155,  50, 175),   # purple
    "HEALER":   ( 90, 200, 130),   # green
    "SCHOLAR":  ( 90, 160, 230),   # blue
    "ARTIST":   (240, 170,  70),   # amber
    "DIPLOMAT": (200, 200, 110),   # pale yellow
}
ARCHETYPE_SHORT: dict[str, str] = {
    "WARRIOR":  "WAR",
    "TYRANT":   "TYR",
    "HEALER":   "HEA",
    "SCHOLAR":  "SCH",
    "ARTIST":   "ART",
    "DIPLOMAT": "DIP",
}


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
    archetype: str = ""     # WARRIOR / SCHOLAR / HEALER / TYRANT / ARTIST / DIPLOMAT
    rationale: str = ""     # one-line biographical flavor connecting person to mechanic
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

        # Archetype badge top-right.
        archetype = (self.archetype or "").upper()
        if archetype in ARCHETYPE_COLORS:
            arch_color = ARCHETYPE_COLORS[archetype]
            short = ARCHETYPE_SHORT[archetype]
            arch_rect = pygame.Rect(inner.right - 36, inner.y + 4, 32, 14)
            pygame.draw.rect(surface, BG_DARK, arch_rect)
            pygame.draw.rect(surface, arch_color, arch_rect, width=1)
            font_arch = pygame.font.SysFont("arial", 8, bold=True)
            arch_surf = font_arch.render(short, True, arch_color)
            surface.blit(arch_surf, arch_surf.get_rect(center=arch_rect.center))

        # Status / ORDER icon strip above the title.
        # Only renders if there's something to show — keeps card clean otherwise.
        self._draw_status_strip(surface, inner, bottom_band_h)

    def _status_stacks(self) -> list[tuple[str, int]]:
        """Return [(STATUS_NAME, stack_count), ...] for statuses to surface.

        Booleans become count=1. Zero/missing statuses are filtered out.
        Order matches SUPPORTED_STATUSES so the strip layout is stable.
        """
        raw = self.statuses or {}
        out: list[tuple[str, int]] = []
        for name in SUPPORTED_STATUSES:
            value = raw.get(name, 0)
            if isinstance(value, bool):
                if value:
                    out.append((name, 1))
                continue
            try:
                n = int(value)
            except Exception:
                n = 0
            if n > 0:
                out.append((name, n))
        return out

    def _draw_status_strip(
        self,
        surface: pygame.Surface,
        inner: pygame.Rect,
        bottom_band_h: int,
    ) -> None:
        stacks = self._status_stacks()
        order_ready = bool(getattr(self, "order_ready", False))
        if not stacks and not order_ready:
            return

        # Strip sits in the band just above the title strip.
        strip_h = 14
        icon_size = 11
        gap = 1
        strip_top = inner.bottom - bottom_band_h - strip_h - 1
        slot_x = inner.x + 3
        slot_w = icon_size + 2
        right_limit = inner.right - 4
        label_font = pygame.font.SysFont("arial", 7, bold=True)

        # ORDER indicator first (left edge), glows green when usable.
        if order_ready:
            self._draw_strip_icon(
                surface,
                slot_x,
                strip_top,
                icon_size,
                strip_h,
                trigger_name="ORDER",
                fallback_letter="O",
                border_color=NEON_GREEN,
            )
            slot_x += slot_w + 2  # extra breathing room before statuses

        for idx, (name, count) in enumerate(stacks):
            # If next slot won't fit, show "+N" overflow chip and stop.
            remaining = len(stacks) - idx
            if slot_x + slot_w > right_limit and remaining > 0:
                overflow = label_font.render(f"+{remaining}", True, GOLD)
                surface.blit(
                    overflow,
                    (right_limit - overflow.get_width(), strip_top + strip_h - overflow.get_height() - 1),
                )
                break
            self._draw_strip_icon(
                surface,
                slot_x,
                strip_top,
                icon_size,
                strip_h,
                status_name=name,
                fallback_letter=name[:1],
                border_color=GOLD,
            )
            if count > 1:
                num_surf = label_font.render(str(count), True, WHITE_TEXT)
                # Tiny pill behind the count so it reads on any artwork colour.
                pill = pygame.Rect(
                    slot_x + slot_w - num_surf.get_width() - 1,
                    strip_top + strip_h - num_surf.get_height() - 1,
                    num_surf.get_width() + 2,
                    num_surf.get_height() + 1,
                )
                pygame.draw.rect(surface, BG_DARK, pill)
                pygame.draw.rect(surface, GOLD, pill, width=1)
                surface.blit(num_surf, (pill.x + 1, pill.y))
            slot_x += slot_w + gap

    @staticmethod
    def _draw_strip_icon(
        surface: pygame.Surface,
        x: int,
        y: int,
        icon_size: int,
        strip_h: int,
        *,
        status_name: str | None = None,
        trigger_name: str | None = None,
        fallback_letter: str = "?",
        border_color: tuple[int, int, int] = GOLD,
    ) -> None:
        # Background slot with thin border in the strip colour.
        slot_rect = pygame.Rect(x, y, icon_size + 2, strip_h)
        pygame.draw.rect(surface, BG_DARK, slot_rect)
        pygame.draw.rect(surface, border_color, slot_rect, width=1)

        icon: pygame.Surface | None = None
        if status_name is not None:
            icon = get_status_icon(status_name, size=icon_size)
        elif trigger_name is not None:
            icon = get_trigger_icon(trigger_name, size=icon_size)

        if icon is not None:
            surface.blit(icon, (x + 1, y + (strip_h - icon_size) // 2))
        else:
            # Text fallback: first letter of the status name.
            font = pygame.font.SysFont("arial", icon_size - 2, bold=True)
            letter = font.render(fallback_letter, True, border_color)
            surface.blit(letter, letter.get_rect(center=slot_rect.center))
