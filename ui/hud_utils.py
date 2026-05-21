"""Professional HUD layout with side panels - no overlaps."""

import pygame
from config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    BG_DARK,
    BG_MID,
    BG_LIGHT,
    NEON_GREEN,
    NEON_RED,
    NEON_BLUE,
    WHITE_TEXT,
    MUTED_TEXT,
    GOLD,
    DIVIDER_Y,
)
from ui.effects import draw_drop_shadow, draw_glow, draw_text_shadow


def draw_player_panel(
    screen: pygame.Surface,
    player_name: str,
    hand_count: int,
    deck_count: int,
    discard_count: int,
    field_count: int,
    field_hp: int,
    score: int,
    is_active: bool,
    is_p1: bool,
    fonts: dict,
) -> None:
    """Draw professional player info panel on the side."""
    # Layout: P2 top-left, P1 bottom-left
    panel_width = 240
    panel_height = 70
    margin = 12

    if is_p1:
        panel_x = margin
        panel_y = SCREEN_HEIGHT - panel_height - margin
    else:
        panel_x = margin
        panel_y = margin

    panel_rect = pygame.Rect(panel_x, panel_y, panel_width, panel_height)
    panel_color = NEON_GREEN if is_active else NEON_BLUE
    text_color = WHITE_TEXT

    # Draw panel with professional styling
    draw_drop_shadow(screen, panel_rect, offset=(3, 3), size=6, alpha=120)
    if is_active:
        draw_glow(screen, panel_rect, panel_color, glow_size=6, alpha=140)

    pygame.draw.rect(screen, BG_MID, panel_rect, border_radius=6)
    pygame.draw.rect(screen, panel_color, panel_rect, width=2, border_radius=6)

    # Player name (big, bold)
    name_font = pygame.font.SysFont("arial", 14, bold=True)
    name_surf = name_font.render(player_name, True, panel_color)
    screen.blit(name_surf, (panel_x + 10, panel_y + 6))

    # Stats line: H:6 D:15 X:0 F:3
    stat_font = pygame.font.SysFont("arial", 10, bold=False)
    stats_text = f"H:{hand_count} D:{deck_count} X:{discard_count} F:{field_count}"
    stats_surf = stat_font.render(stats_text, True, MUTED_TEXT)
    screen.blit(stats_surf, (panel_x + 10, panel_y + 24))

    # Score line: HP:0 | Score:10
    score_text = f"HP:{field_hp} | Score:{score}"
    score_surf = stat_font.render(score_text, True, GOLD)
    screen.blit(score_surf, (panel_x + 10, panel_y + 38))


def draw_turn_info(
    screen: pygame.Surface,
    turn: int,
    player_name: str,
    phase: str,
    is_active_p1: bool,
    fonts: dict,
) -> None:
    """Draw turn indicator at top center with opaque background."""
    color = NEON_GREEN if is_active_p1 else NEON_RED
    phase_short = phase.split("_")[0] if phase else "MAIN"

    text = f"Turn {turn}  —  {phase_short}"
    text_font = fonts["big"]
    text_width, text_height = text_font.size(text)
    x = SCREEN_WIDTH // 2 - text_width // 2
    y = 90

    # Draw opaque background rect behind text to prevent card bleed-through
    bg_padding = 8
    bg_rect = pygame.Rect(x - bg_padding, y - bg_padding, text_width + 2 * bg_padding, text_height + 2 * bg_padding)
    bg_surf = pygame.Surface(bg_rect.size, pygame.SRCALPHA)
    bg_surf.fill((0, 0, 0, 200))  # Opaque black with slight transparency for visual blend
    screen.blit(bg_surf, bg_rect.topleft)
    
    # Draw text border for visual separation
    pygame.draw.rect(screen, color, bg_rect, width=1)

    # Draw text with shadow for emphasis
    draw_text_shadow(screen, text_font, text, color, (x, y))


def draw_score_info(
    screen: pygame.Surface,
    p1_field_hp: int,
    p1_score: int,
    p2_field_hp: int,
    p2_score: int,
    fonts: dict,
) -> None:
    """Draw score info at top right with proper positioning to avoid overlaps."""
    panel_width = 180
    panel_height = 70
    margin = 12
    panel_x = SCREEN_WIDTH - panel_width - margin
    panel_y = 140  # Repositioned to clear all widgets and card rows

    panel_rect = pygame.Rect(panel_x, panel_y, panel_width, panel_height)

    # Draw panel with opaque background
    draw_drop_shadow(screen, panel_rect, offset=(3, 3), size=6, alpha=120)
    # Use slightly darker background to ensure readability over cards
    pygame.draw.rect(screen, BG_MID, panel_rect, border_radius=6)
    pygame.draw.rect(screen, NEON_BLUE, panel_rect, width=2, border_radius=6)

    # Labels and values
    label_font = pygame.font.SysFont("arial", 9, bold=True)
    value_font = pygame.font.SysFont("arial", 11, bold=True)

    y = panel_y + 8

    # P2 score
    label = label_font.render("P2 Score:", True, MUTED_TEXT)
    value = value_font.render(str(p2_score), True, NEON_RED)
    screen.blit(label, (panel_x + 8, y))
    screen.blit(value, (panel_x + 120, y))

    # P2 HP
    y += 16
    label = label_font.render("P2 HP:", True, MUTED_TEXT)
    value = value_font.render(str(p2_field_hp), True, NEON_RED)
    screen.blit(label, (panel_x + 8, y))
    screen.blit(value, (panel_x + 120, y))

    # P1 score
    y += 16
    label = label_font.render("P1 Score:", True, MUTED_TEXT)
    value = value_font.render(str(p1_score), True, NEON_GREEN)
    screen.blit(label, (panel_x + 8, y))
    screen.blit(value, (panel_x + 120, y))

    # P1 HP
    y += 16
    label = label_font.render("P1 HP:", True, MUTED_TEXT)
    value = value_font.render(str(p1_field_hp), True, NEON_GREEN)
    screen.blit(label, (panel_x + 8, y))
    screen.blit(value, (panel_x + 120, y))


def draw_zone_backgrounds(screen: pygame.Surface) -> None:
    """Draw very subtle zone backgrounds for visual separation."""
    # P1 zone (bottom) - green tint, very subtle
    p1_zone = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT - DIVIDER_Y), pygame.SRCALPHA)
    p1_zone.fill((0, 80, 0, 4))
    screen.blit(p1_zone, (0, DIVIDER_Y))

    # P2 zone (top) - red tint, very subtle
    p2_zone = pygame.Surface((SCREEN_WIDTH, DIVIDER_Y), pygame.SRCALPHA)
    p2_zone.fill((80, 0, 40, 4))
    screen.blit(p2_zone, (0, 0))
