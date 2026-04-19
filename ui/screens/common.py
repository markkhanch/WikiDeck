import math
from typing import Optional

import pygame

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
)


def draw_background(screen: pygame.Surface, background: Optional[pygame.Surface]) -> None:
    if background is not None:
        screen.blit(background, (0, 0))
    else:
        screen.fill(BG_DARK)


def draw_title(screen: pygame.Surface, text: str, fonts: dict, y: int = 70) -> None:
    t = pygame.time.get_ticks() / 1000.0
    pulse = 0.6 + 0.4 * (0.5 + 0.5 * math.sin(t * 2.0))
    color = (
        int(NEON_GREEN[0] * pulse),
        int(NEON_GREEN[1] * pulse),
        int(NEON_GREEN[2] * pulse),
    )
    surf = fonts["big"].render(text, True, color)
    screen.blit(surf, surf.get_rect(center=(SCREEN_WIDTH // 2, y)))


def draw_button(
    screen: pygame.Surface,
    rect: pygame.Rect,
    text: str,
    fonts: dict,
    *,
    hovered: bool,
    enabled: bool = True,
) -> None:
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
    border = (255, 80, 80) if hovered else MUTED_TEXT
    text_color = border
    pygame.draw.rect(screen, BG_MID, rect)
    pygame.draw.rect(screen, border, rect, width=2)
    label = fonts["med"].render("X", True, text_color)
    screen.blit(label, label.get_rect(center=rect.center))
    return rect
