import pygame

from config import SCREEN_WIDTH, SCREEN_HEIGHT, MUTED_TEXT
from ui.screens.common import (
    draw_background,
    draw_title,
    draw_panel,
    draw_back_hint,
    draw_close_button,
    close_button_rect,
)


def run_settings(
    screen: pygame.Surface,
    fonts: dict,
    background: pygame.Surface | None,
) -> str | None:
    clock = pygame.time.Clock()
    pad = 30
    top = 120
    panel = pygame.Rect(pad, top, SCREEN_WIDTH - pad * 2, 260)

    while True:
        clock.tick(60)
        mx, my = pygame.mouse.get_pos()
        close_rect = close_button_rect()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return "menu"
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and close_rect.collidepoint(mx, my):
                return "menu"

        draw_background(screen, background)
        draw_title(screen, "SETTINGS", fonts, y=70)

        draw_panel(screen, panel, "Audio & Display", fonts)
        rows = [
            "Music: ON",
            "SFX: ON",
            "Fullscreen: OFF",
            "Target FPS: 60",
        ]
        y = panel.y + 48
        for row in rows:
            label = fonts["small"].render(row, True, MUTED_TEXT)
            screen.blit(label, (panel.x + 14, y))
            y += 26

        draw_close_button(screen, fonts, hovered=close_rect.collidepoint(mx, my))
        draw_back_hint(screen, fonts)
        pygame.display.flip()
