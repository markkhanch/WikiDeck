import pygame

from config import (
    BG_DARK,
    GOLD,
    MUTED_TEXT,
    NEON_GREEN,
    NEON_RED,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    WHITE_TEXT,
)
from core.ai_health import get_state as get_ai_state, kick_check as kick_ai_check
from core.sound_player import play_click
from data.settings_service import target_fps
from ui.screens.common import draw_background, draw_title, draw_button, draw_close_button, close_button_rect


_AI_STATUS_COLORS = {
    "online":   NEON_GREEN,
    "offline":  NEON_RED,
    "checking": GOLD,
    "unknown":  MUTED_TEXT,
}


def _draw_ai_status_badge(screen: pygame.Surface, fonts: dict) -> pygame.Rect:
    """Render a small status pill in the top-right corner. Click to re-check."""
    state = get_ai_state()
    status = str(state.get("status", "unknown"))
    message = str(state.get("message", ""))
    color = _AI_STATUS_COLORS.get(status, MUTED_TEXT)
    font = fonts["small"]
    text = font.render(message, True, color)
    pad_x, pad_y = 10, 6
    badge = pygame.Rect(0, 0, text.get_width() + pad_x * 2, text.get_height() + pad_y * 2)
    badge.topleft = (16, 16)
    pygame.draw.rect(screen, BG_DARK, badge)
    pygame.draw.rect(screen, color, badge, width=2)
    screen.blit(text, (badge.x + pad_x, badge.y + pad_y))
    hint = font.render("click to recheck", True, MUTED_TEXT)
    screen.blit(hint, (badge.x + 2, badge.bottom + 2))
    # Extend the click-target a bit so the hint line is clickable too.
    return badge.inflate(0, hint.get_height() + 4)


def run_main_menu(
    screen: pygame.Surface,
    fonts: dict,
    background: pygame.Surface | None,
) -> str | None:
    clock = pygame.time.Clock()
    items = [
        ("PLAY", "play"),
        ("HOST GAME", "host_game"),
        ("JOIN GAME", "join_game"),
        ("COLLECTION", "collection"),
        ("DECK BUILDER", "deck_builder"),
        ("SHOP", "shop"),
        ("PROFILE", "profile"),
    ]

    button_w, button_h = 300, 50
    spacing = 14
    start_y = 210
    buttons: list[tuple[pygame.Rect, str]] = []
    for i, (_, key) in enumerate(items):
        x = (SCREEN_WIDTH - button_w) // 2
        y = start_y + i * (button_h + spacing)
        buttons.append((pygame.Rect(x, y, button_w, button_h), key))

    settings_rect = pygame.Rect(SCREEN_WIDTH - 160, SCREEN_HEIGHT - 60, 140, 36)
    ai_badge_rect = pygame.Rect(0, 0, 0, 0)

    # Whenever the menu opens, refresh the AI health check so the badge
    # reflects current network state, not whatever was true at app start.
    kick_ai_check()

    while True:
        clock.tick(target_fps())
        mx, my = pygame.mouse.get_pos()
        close_rect = close_button_rect()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return None
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if close_rect.collidepoint(mx, my):
                    play_click()
                    return None
                if ai_badge_rect.collidepoint(mx, my):
                    play_click()
                    kick_ai_check(force=True)
                    continue
                for rect, key in buttons:
                    if rect.collidepoint(mx, my):
                        play_click()
                        return key
                if settings_rect.collidepoint(mx, my):
                    play_click()
                    return "settings"

        draw_background(screen, background)
        # Place a larger logo centered above the PLAY button
        logo_max_h = 300
        # Positive value moves logo down, negative moves it up
        logo_offset = 80
        logo_y = start_y - logo_max_h - 16 + logo_offset
        draw_title(screen, "WIKIDECK", fonts, y=logo_y, max_height=logo_max_h)

        for (label, _), (rect, _) in zip(items, buttons):
            draw_button(screen, rect, label, fonts, hovered=rect.collidepoint(mx, my))

        draw_button(
            screen,
            settings_rect,
            "SETTINGS",
            fonts,
            hovered=settings_rect.collidepoint(mx, my),
        )
        draw_close_button(screen, fonts, hovered=close_rect.collidepoint(mx, my))
        ai_badge_rect = _draw_ai_status_badge(screen, fonts)

        pygame.display.flip()
