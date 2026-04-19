import pygame

from config import SCREEN_WIDTH, SCREEN_HEIGHT, MUTED_TEXT, GOLD, NEON_BLUE, BG_MID
from ui.screens.common import (
    draw_background,
    draw_title,
    draw_panel,
    draw_back_hint,
    draw_close_button,
    close_button_rect,
)


def run_profile(
    screen: pygame.Surface,
    fonts: dict,
    background: pygame.Surface | None,
) -> str | None:
    clock = pygame.time.Clock()
    pad = 30
    top = 120
    info_rect = pygame.Rect(pad, top, SCREEN_WIDTH - pad * 2, 140)
    history_rect = pygame.Rect(pad, info_rect.bottom + 16, SCREEN_WIDTH - pad * 2, 220)

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
        draw_title(screen, "PROFILE", fonts, y=70)

        draw_panel(screen, info_rect, "Player Profile", fonts)
        draw_panel(screen, history_rect, "Match History (last 20)", fonts)

        label = fonts["small"].render("Level 3  •  XP 240/500  •  Gold 120  •  Total Cards 20", True, MUTED_TEXT)
        screen.blit(label, (info_rect.x + 10, info_rect.y + 40))

        bar_rect = pygame.Rect(info_rect.x + 10, info_rect.y + 70, info_rect.width - 20, 18)
        pygame.draw.rect(screen, BG_MID, bar_rect)
        pygame.draw.rect(screen, NEON_BLUE, bar_rect, width=2)
        fill = pygame.Rect(bar_rect.x + 2, bar_rect.y + 2, int((bar_rect.width - 4) * 0.48), bar_rect.height - 4)
        pygame.draw.rect(screen, GOLD, fill)

        note = fonts["small"].render("Card mastery & detailed stats coming soon", True, MUTED_TEXT)
        screen.blit(note, (history_rect.x + 10, history_rect.bottom - 26))

        draw_close_button(screen, fonts, hovered=close_rect.collidepoint(mx, my))
        draw_back_hint(screen, fonts)
        pygame.display.flip()
