import pygame

from config import SCREEN_WIDTH, SCREEN_HEIGHT, CARD_WIDTH, CARD_HEIGHT, MUTED_TEXT, GOLD
from core.card import Card
from core.card_factory import build_card_from_spec
from data.db import get_cached_card, get_collection
from ui.components.hover_panel import draw_hover_panel
from ui.screens.common import (
    draw_background,
    draw_title,
    draw_panel,
    draw_back_hint,
    draw_close_button,
    close_button_rect,
)


def _build_grid_cards(collection: list[dict]) -> list[tuple[Card, dict]]:
    cards: list[tuple[Card, dict]] = []
    for entry in collection:
        spec = get_cached_card(entry["title"], entry["rarity"])
        if spec is None:
            continue
        cards.append((build_card_from_spec(spec), entry))
    return cards


def run_collection(
    screen: pygame.Surface,
    fonts: dict,
    background: pygame.Surface | None,
) -> str | None:
    clock = pygame.time.Clock()

    filter_bar = pygame.Rect(40, 120, SCREEN_WIDTH - 80, 40)
    list_top = filter_bar.bottom + 16
    list_h = SCREEN_HEIGHT - list_top - 60
    list_rect = pygame.Rect(40, list_top, SCREEN_WIDTH - 80, list_h)
    grid_rect = pygame.Rect(list_rect.x + 10, list_rect.y + 34, list_rect.width - 20, list_rect.height - 44)

    scroll = 0
    cached_signature: tuple[tuple[str, str, int], ...] = ()
    grid_cards: list[tuple[Card, dict]] = []

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
            if event.type == pygame.MOUSEWHEEL and list_rect.collidepoint(mx, my):
                scroll = max(0, scroll - event.y * 40)

        draw_background(screen, background)
        draw_title(screen, "COLLECTION", fonts, y=70)

        draw_panel(screen, filter_bar, "Filters: Theme | Rarity | Trigger | Search", fonts)
        draw_panel(screen, list_rect, "Owned Cards", fonts)

        collection = get_collection()
        signature = tuple((entry["title"], entry["rarity"], int(entry["count"])) for entry in collection)
        if signature != cached_signature:
            grid_cards = _build_grid_cards(collection)
            cached_signature = signature

        cols = max(1, grid_rect.width // (CARD_WIDTH + 14))
        rows = (len(grid_cards) + cols - 1) // cols
        content_h = rows * (CARD_HEIGHT + 28)
        visible_h = max(1, grid_rect.height)
        max_scroll = max(0, content_h - visible_h)
        scroll = min(scroll, max_scroll)

        prev_clip = screen.get_clip()
        screen.set_clip(grid_rect)
        hovered_card: Card | None = None
        for idx, (card, entry) in enumerate(grid_cards):
            col = idx % cols
            row = idx // cols
            x = grid_rect.x + col * (CARD_WIDTH + 14)
            y = grid_rect.y + row * (CARD_HEIGHT + 28) - scroll
            if y + CARD_HEIGHT < grid_rect.y or y > grid_rect.bottom:
                continue
            card.set_topleft(x, y)
            card.draw(screen)
            qty = fonts["small"].render(f"×{entry['count']}", True, GOLD)
            screen.blit(qty, (x + 2, y + CARD_HEIGHT + 3))
            if card.rect.collidepoint(mx, my):
                hovered_card = card
        screen.set_clip(prev_clip)

        hint = fonts["small"].render(
            f"Mouse wheel to scroll ({scroll}/{max_scroll})",
            True,
            MUTED_TEXT,
        )
        screen.blit(hint, (40, SCREEN_HEIGHT - 34))

        draw_close_button(screen, fonts, hovered=close_rect.collidepoint(mx, my))
        draw_back_hint(screen, fonts)
        if hovered_card is not None:
            draw_hover_panel(screen, hovered_card, fonts, hovered_card.rect)
        pygame.display.flip()
