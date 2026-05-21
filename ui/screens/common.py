import math
from typing import Optional
import os

import pygame

from data.settings_service import get_bool
from ui.effects import draw_drop_shadow, draw_glow, draw_text_shadow
from config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    BG_DARK,
    BG_MID,
    BG_LIGHT,
    NEON_BLUE,
    NEON_GREEN,
    WHITE_TEXT,
    MUTED_TEXT,
    IMAGES_DIR,
)

def draw_background(screen: pygame.Surface, background: Optional[pygame.Surface]) -> None:
    if background is not None:
        screen.blit(background, (0, 0))
    else:
        screen.fill(BG_DARK)


def draw_title(screen: pygame.Surface, text: str, fonts: dict, y: int = 70, max_height: Optional[int] = None) -> None:
    if get_bool("display.animations"):
        t = pygame.time.get_ticks() / 1000.0
        pulse = 0.6 + 0.4 * (0.5 + 0.5 * math.sin(t * 2.0))
    else:
        pulse = 1.0
    color = (
        int(NEON_GREEN[0] * pulse),
        int(NEON_GREEN[1] * pulse),
        int(NEON_GREEN[2] * pulse),
    )
    # Try to load and draw a logo image instead of text if available.
    # Cache the loaded surface in a module-level variable to avoid reloading every frame.
    global _logo_surface
    try:
        _logo_surface
    except NameError:
        _logo_surface = None

    if _logo_surface is None:
        logo_path = os.path.join(IMAGES_DIR, "logo.png")
        if os.path.isfile(logo_path):
            try:
                surf = pygame.image.load(logo_path)
                try:
                    surf = surf.convert_alpha()
                except pygame.error:
                    pass
                _logo_surface = surf
            except pygame.error:
                _logo_surface = None

    if _logo_surface:
        surf = _logo_surface
        if max_height is not None and max_height > 0:
            iw, ih = surf.get_size()
            scale = max_height / ih
            new_w = max(1, int(iw * scale))
            new_h = max(1, int(ih * scale))
            try:
                surf = pygame.transform.smoothscale(surf, (new_w, new_h))
            except Exception:
                surf = pygame.transform.scale(surf, (new_w, new_h))
        rect = surf.get_rect(midtop=(SCREEN_WIDTH // 2, y))
        screen.blit(surf, rect)
    else:
        draw_text_shadow(screen, fonts["big"], text, color, (SCREEN_WIDTH // 2 - fonts["big"].size(text)[0] // 2, y))


def draw_button(
    screen: pygame.Surface,
    rect: pygame.Rect,
    text: str,
    fonts: dict,
    *,
    hovered: bool,
    enabled: bool = True,
) -> None:
    draw_drop_shadow(screen, rect, offset=(3, 3), size=6, alpha=120)
    if hovered and enabled:
        draw_glow(screen, rect, NEON_GREEN, glow_size=8, alpha=180)

    border = NEON_GREEN if hovered and enabled else MUTED_TEXT
    text_color = NEON_GREEN if hovered and enabled else WHITE_TEXT
    if not enabled:
        border = MUTED_TEXT
        text_color = MUTED_TEXT
    pygame.draw.rect(screen, BG_MID, rect)
    pygame.draw.rect(screen, border, rect, width=2)
    label = fonts["med"].render(text, True, text_color)
    screen.blit(label, label.get_rect(center=rect.center))


def draw_panel(screen: pygame.Surface, rect: pygame.Rect, title: str, fonts: dict) -> None:
    draw_drop_shadow(screen, rect, offset=(3, 3), size=6, alpha=100)
    draw_glow(screen, rect, NEON_BLUE, glow_size=4, alpha=100)
    pygame.draw.rect(screen, BG_MID, rect)
    pygame.draw.rect(screen, NEON_BLUE, rect, width=2)
    if title:
        label = fonts["small"].render(title, True, WHITE_TEXT)
        screen.blit(label, (rect.x + 10, rect.y + 8))


def draw_back_hint(screen: pygame.Surface, fonts: dict) -> None:
    label = fonts["small"].render("Esc — Back", True, MUTED_TEXT)
    screen.blit(label, (SCREEN_WIDTH - label.get_width() - 12, SCREEN_HEIGHT - 22))


def close_button_rect() -> pygame.Rect:
    return pygame.Rect(SCREEN_WIDTH - 46, 10, 36, 36)


def draw_close_button(screen: pygame.Surface, fonts: dict, *, hovered: bool) -> pygame.Rect:
    rect = close_button_rect()
    draw_drop_shadow(screen, rect, offset=(2, 2), size=4, alpha=120)
    if hovered:
        draw_glow(screen, rect, (255, 80, 80), glow_size=6, alpha=160)

    border = (255, 80, 80) if hovered else MUTED_TEXT
    text_color = border
    pygame.draw.rect(screen, BG_MID, rect)
    pygame.draw.rect(screen, border, rect, width=2)
    label = fonts["med"].render("X", True, text_color)
    screen.blit(label, label.get_rect(center=rect.center))
    return rect
