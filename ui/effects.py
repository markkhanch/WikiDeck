"""Visual effects utilities for UI polish — glows, shadows, borders, animations."""

import pygame
import math
from config import RARITY_COLORS


def ease_out_cubic(t: float) -> float:
    """Easing function: starts fast, ends slow. t: [0, 1]"""
    t = max(0, min(1, t))
    return 1 - (1 - t) ** 3


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation between a and b, t: [0, 1]"""
    return a + (b - a) * t


def lerp_rect(rect_from: pygame.Rect, rect_to: pygame.Rect, t: float) -> pygame.Rect:
    """Interpolate between two rects."""
    t = max(0, min(1, t))
    x = lerp(rect_from.x, rect_to.x, t)
    y = lerp(rect_from.y, rect_to.y, t)
    w = lerp(rect_from.width, rect_to.width, t)
    h = lerp(rect_from.height, rect_to.height, t)
    return pygame.Rect(x, y, w, h)


def draw_drop_shadow(
    surface: pygame.Surface,
    rect: pygame.Rect,
    offset: tuple[int, int] = (3, 3),
    size: int = 6,
    alpha: int = 120,
) -> None:
    """Draw a soft drop shadow behind a rect by blitting semi-transparent shadow layers."""
    if size <= 0:
        return

    shadow_color = (0, 0, 0)
    shadow_surface = pygame.Surface((rect.width + size * 2, rect.height + size * 2), pygame.SRCALPHA)

    for layer in range(size, 0, -1):
        layer_alpha = int(alpha * (1 - layer / size) * 0.6)
        pygame.draw.rect(
            shadow_surface,
            (*shadow_color, layer_alpha),
            pygame.Rect(size - layer, size - layer, rect.width + layer * 2, rect.height + layer * 2),
            border_radius=8,
        )

    shadow_rect = shadow_surface.get_rect(topleft=(rect.x - size + offset[0], rect.y - size + offset[1]))
    surface.blit(shadow_surface, shadow_rect)


def draw_glow(
    surface: pygame.Surface,
    rect: pygame.Rect,
    color: tuple[int, int, int],
    glow_size: int = 8,
    alpha: int = 180,
) -> None:
    """Draw a soft glow around a rect by blitting semi-transparent circles."""
    if glow_size <= 0:
        return

    glow_surface = pygame.Surface((rect.width + glow_size * 2, rect.height + glow_size * 2), pygame.SRCALPHA)
    center_x = rect.width // 2 + glow_size
    center_y = rect.height // 2 + glow_size

    for layer in range(glow_size, 0, -1):
        layer_alpha = int(alpha * (1 - layer / glow_size) * 0.4)
        radius = glow_size // 2 + layer
        pygame.draw.circle(glow_surface, (*color, layer_alpha), (center_x, center_y), radius)

    glow_rect = glow_surface.get_rect(topleft=(rect.x - glow_size, rect.y - glow_size))
    surface.blit(glow_surface, glow_rect)


def draw_rarity_border(
    surface: pygame.Surface,
    rect: pygame.Rect,
    rarity: str | None,
    width: int = 3,
    alpha: int = 255,
) -> None:
    """Draw a colored border based on card rarity."""
    if not rarity or rarity not in RARITY_COLORS:
        return

    color = RARITY_COLORS[rarity]
    if alpha < 255:
        border_surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(border_surface, (*color, alpha), border_surface.get_rect(), width, border_radius=8)
        surface.blit(border_surface, rect)
    else:
        pygame.draw.rect(surface, color, rect, width, border_radius=8)


def draw_text_shadow(
    surface: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    color: tuple[int, int, int],
    pos: tuple[int, int],
    shadow_offset: tuple[int, int] = (2, 2),
    shadow_color: tuple[int, int, int] = (0, 0, 0),
    shadow_alpha: int = 150,
) -> pygame.Rect:
    """Draw text with a shadow. Returns text rect."""
    shadow_surf = font.render(text, True, shadow_color)
    shadow_surf.set_alpha(shadow_alpha)
    surface.blit(shadow_surf, (pos[0] + shadow_offset[0], pos[1] + shadow_offset[1]))

    text_surf = font.render(text, True, color)
    text_rect = text_surf.get_rect(topleft=pos)
    surface.blit(text_surf, text_rect)
    return text_rect
