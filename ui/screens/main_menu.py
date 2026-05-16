import pygame

from config import SCREEN_WIDTH, SCREEN_HEIGHT
from core.sound_player import play_click
from data.settings_service import target_fps
from ui.screens.common import draw_background, draw_title, draw_button, draw_close_button, close_button_rect


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
                for rect, key in buttons:
                    if rect.collidepoint(mx, my):
                        play_click()
                        return key
                if settings_rect.collidepoint(mx, my):
                    play_click()
                    return "settings"

        draw_background(screen, background)
        draw_title(screen, "WIKIDECK", fonts, y=90)

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

        pygame.display.flip()
