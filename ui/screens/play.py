import math
import pygame

from config import SCREEN_WIDTH, SCREEN_HEIGHT, NEON_GREEN
from core.sound_player import play_click
from data.settings_service import target_fps, get_bool
from ui.screens.common import (
    draw_background,
    draw_button,
    draw_back_hint,
    draw_close_button,
    close_button_rect,
)
from ui.effects import draw_text_shadow


def run_play_menu(
    screen: pygame.Surface,
    fonts: dict,
    background: pygame.Surface | None,
    deck_size: int,
    deck_min: int,
) -> str | None:
    clock = pygame.time.Clock()
    items = [
        ("QUICK MATCH", "match"),
        ("FRIEND MATCH", "friend"),
        ("PRACTICE", "practice"),
    ]

    button_w, button_h = 360, 50
    spacing = 14
    start_y = 220
    buttons: list[tuple[pygame.Rect, str]] = []
    for i, (_, key) in enumerate(items):
        x = (SCREEN_WIDTH - button_w) // 2
        y = start_y + i * (button_h + spacing)
        buttons.append((pygame.Rect(x, y, button_w, button_h), key))

    status_msg = ""
    while True:
        clock.tick(target_fps())
        mx, my = pygame.mouse.get_pos()
        close_rect = close_button_rect()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                play_click()
                return "menu"
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if close_rect.collidepoint(mx, my):
                    play_click()
                    return "menu"
                for rect, key in buttons:
                    if rect.collidepoint(mx, my):
                        play_click()
                        if key == "match":
                            if deck_size < deck_min:
                                status_msg = f"Deck too small: {deck_size}/{deck_min}"
                                break
                            return "match"
                        status_msg = "Not implemented in MVP"

        draw_background(screen, background)
        # Draw a semi-opaque overlay in the center to hide any large logo watermark
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        screen.blit(overlay, (0, 0))
        # Draw text title (no logo) for this screen
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
        text = "PLAY"
        x = SCREEN_WIDTH // 2 - fonts["big"].size(text)[0] // 2
        draw_text_shadow(screen, fonts["big"], text, color, (x, 90))

        for (label, _), (rect, _) in zip(items, buttons):
            draw_button(screen, rect, label, fonts, hovered=rect.collidepoint(mx, my))

        if status_msg:
            msg = fonts["small"].render(status_msg, True, (255, 215, 0))
            screen.blit(msg, msg.get_rect(center=(SCREEN_WIDTH // 2, 420)))

        draw_close_button(screen, fonts, hovered=close_rect.collidepoint(mx, my))
        draw_back_hint(screen, fonts)
        pygame.display.flip()
