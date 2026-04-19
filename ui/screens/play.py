import pygame

from config import SCREEN_WIDTH
from ui.screens.common import (
    draw_background,
    draw_title,
    draw_button,
    draw_back_hint,
    draw_close_button,
    close_button_rect,
)


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
        clock.tick(60)
        mx, my = pygame.mouse.get_pos()
        close_rect = close_button_rect()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return "menu"
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if close_rect.collidepoint(mx, my):
                    return "menu"
                for rect, key in buttons:
                    if rect.collidepoint(mx, my):
                        if key == "match":
                            if deck_size < deck_min:
                                status_msg = f"Deck too small: {deck_size}/{deck_min}"
                                break
                            return "match"
                        status_msg = "Not implemented in MVP"

        draw_background(screen, background)
        draw_title(screen, "PLAY", fonts, y=90)

        for (label, _), (rect, _) in zip(items, buttons):
            draw_button(screen, rect, label, fonts, hovered=rect.collidepoint(mx, my))

        if status_msg:
            msg = fonts["small"].render(status_msg, True, (255, 215, 0))
            screen.blit(msg, msg.get_rect(center=(SCREEN_WIDTH // 2, 420)))

        draw_close_button(screen, fonts, hovered=close_rect.collidepoint(mx, my))
        draw_back_hint(screen, fonts)
        pygame.display.flip()
