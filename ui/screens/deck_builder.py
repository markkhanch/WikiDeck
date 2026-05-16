import pygame

from config import SCREEN_WIDTH, SCREEN_HEIGHT, CARD_WIDTH, CARD_HEIGHT, MUTED_TEXT, GOLD
from core.sound_player import play_click
from core.card import Card
from core.card_factory import build_card_from_spec
from data.db import add_to_deck, deck_size, get_cached_card, get_collection, get_deck_cards, set_deck_count
from data.settings_service import get_int, target_fps
from ui.components.hover_panel import draw_hover_panel
from ui.screens.common import (
    draw_background,
    draw_title,
    draw_panel,
    draw_back_hint,
    draw_close_button,
    close_button_rect,
)


def _build_grid_cards(entries: list[dict]) -> list[tuple[Card, dict]]:
    cards: list[tuple[Card, dict]] = []
    for entry in entries:
        spec = get_cached_card(entry["title"], entry["rarity"])
        if spec is None:
            continue
        cards.append((build_card_from_spec(spec), entry))
    return cards


def run_deck_builder(
    screen: pygame.Surface,
    fonts: dict,
    background: pygame.Surface | None,
) -> str | None:
    clock = pygame.time.Clock()
    pad = 30
    top = 120

    left_w = int(SCREEN_WIDTH * 0.60)
    right_w = SCREEN_WIDTH - left_w - pad * 3
    left_rect = pygame.Rect(pad, top, left_w, SCREEN_HEIGHT - top - 80)
    right_rect = pygame.Rect(left_rect.right + pad, top, right_w, SCREEN_HEIGHT - top - 160)
    stats_rect = pygame.Rect(right_rect.x, right_rect.bottom + 12, right_rect.width, 68)
    left_grid = pygame.Rect(left_rect.x + 10, left_rect.y + 34, left_rect.width - 20, left_rect.height - 44)
    right_grid = pygame.Rect(right_rect.x + 10, right_rect.y + 34, right_rect.width - 20, right_rect.height - 44)

    left_scroll = 0
    right_scroll = 0
    left_signature: tuple[tuple[str, str, int], ...] = ()
    right_signature: tuple[tuple[str, str, int], ...] = ()
    left_cards: list[tuple[Card, dict]] = []
    right_cards: list[tuple[Card, dict]] = []

    while True:
        clock.tick(target_fps())
        mx, my = pygame.mouse.get_pos()
        close_rect = close_button_rect()
        deck_min = get_int("gameplay.deck_min")
        deck_max = get_int("gameplay.deck_max")
        click_pos = None
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                play_click()
                return "menu"
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and close_rect.collidepoint(mx, my):
                play_click()
                return "menu"
            if event.type == pygame.MOUSEWHEEL:
                if left_rect.collidepoint(mx, my):
                    left_scroll = max(0, left_scroll - event.y * 40)
                elif right_rect.collidepoint(mx, my):
                    right_scroll = max(0, right_scroll - event.y * 40)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                click_pos = event.pos

        draw_background(screen, background)
        draw_title(screen, "DECK BUILDER", fonts, y=70)

        draw_panel(screen, left_rect, "Collection (click card to add)", fonts)
        draw_panel(screen, right_rect, "Active Deck (click card to remove)", fonts)
        draw_panel(screen, stats_rect, "Deck Stats", fonts)

        collection = get_collection()
        deck_cards = get_deck_cards()
        deck_map = {(c["title"], c["rarity"]): c["count"] for c in deck_cards}
        coll_map = {(c["title"], c["rarity"]): c["count"] for c in collection}

        new_left_signature = tuple((entry["title"], entry["rarity"], int(entry["count"])) for entry in collection)
        if new_left_signature != left_signature:
            left_cards = _build_grid_cards(collection)
            left_signature = new_left_signature
        new_right_signature = tuple((entry["title"], entry["rarity"], int(entry["count"])) for entry in deck_cards)
        if new_right_signature != right_signature:
            right_cards = _build_grid_cards(deck_cards)
            right_signature = new_right_signature

        left_cols = max(1, left_grid.width // (CARD_WIDTH + 14))
        left_rows = (len(left_cards) + left_cols - 1) // left_cols
        left_max_scroll = max(0, left_rows * (CARD_HEIGHT + 28) - left_grid.height)
        left_scroll = min(left_scroll, left_max_scroll)

        right_cols = max(1, right_grid.width // (CARD_WIDTH + 14))
        right_rows = (len(right_cards) + right_cols - 1) // right_cols
        right_max_scroll = max(0, right_rows * (CARD_HEIGHT + 28) - right_grid.height)
        right_scroll = min(right_scroll, right_max_scroll)

        hovered_card: Card | None = None
        left_clickables: list[tuple[pygame.Rect, dict]] = []
        right_clickables: list[tuple[pygame.Rect, dict]] = []

        prev_clip = screen.get_clip()
        screen.set_clip(left_grid)
        for idx, (card, entry) in enumerate(left_cards):
            col = idx % left_cols
            row = idx // left_cols
            x = left_grid.x + col * (CARD_WIDTH + 14)
            y = left_grid.y + row * (CARD_HEIGHT + 28) - left_scroll
            if y + CARD_HEIGHT < left_grid.y or y > left_grid.bottom:
                continue
            card.set_topleft(x, y)
            card.draw(screen)
            owned = coll_map.get((entry["title"], entry["rarity"]), 0)
            in_deck = deck_map.get((entry["title"], entry["rarity"]), 0)
            qty = fonts["small"].render(f"{in_deck}/{owned}", True, GOLD)
            screen.blit(qty, (x + 2, y + CARD_HEIGHT + 3))
            left_clickables.append((pygame.Rect(x, y, CARD_WIDTH, CARD_HEIGHT), entry))
            if card.rect.collidepoint(mx, my):
                hovered_card = card
        screen.set_clip(prev_clip)

        prev_clip = screen.get_clip()
        screen.set_clip(right_grid)
        for idx, (card, entry) in enumerate(right_cards):
            col = idx % right_cols
            row = idx // right_cols
            x = right_grid.x + col * (CARD_WIDTH + 14)
            y = right_grid.y + row * (CARD_HEIGHT + 28) - right_scroll
            if y + CARD_HEIGHT < right_grid.y or y > right_grid.bottom:
                continue
            card.set_topleft(x, y)
            card.draw(screen)
            qty = fonts["small"].render(f"×{entry['count']}", True, GOLD)
            screen.blit(qty, (x + 2, y + CARD_HEIGHT + 3))
            right_clickables.append((pygame.Rect(x, y, CARD_WIDTH, CARD_HEIGHT), entry))
            if card.rect.collidepoint(mx, my):
                hovered_card = card
        screen.set_clip(prev_clip)

        if click_pos:
            cx, cy = click_pos
            for rect, entry in left_clickables:
                if rect.collidepoint(cx, cy):
                    total = deck_size()
                    if total < deck_max:
                        owned = coll_map.get((entry["title"], entry["rarity"]), 0)
                        in_deck = deck_map.get((entry["title"], entry["rarity"]), 0)
                        if in_deck < owned:
                            add_to_deck(entry["title"], entry["rarity"], 1)
                    break
            for rect, entry in right_clickables:
                if rect.collidepoint(cx, cy):
                    set_deck_count(entry["title"], entry["rarity"], int(entry["count"]) - 1)
                    break

        total = deck_size()
        warn = ""
        if total < deck_min:
            warn = f"Deck too small: {total}/{deck_min}"
        elif total > deck_max:
            warn = f"Deck too large: {total}/{deck_max}"
        stats = fonts["small"].render(f"Cards: {total} (min {deck_min}, max {deck_max})", True, MUTED_TEXT)
        screen.blit(stats, (stats_rect.x + 10, stats_rect.y + 30))
        if warn:
            warn_surf = fonts["small"].render(warn, True, GOLD)
            screen.blit(warn_surf, (stats_rect.x + 10, stats_rect.y + 48))

        scroll_hint = fonts["small"].render(
            f"Scroll L:{left_scroll}/{left_max_scroll}  R:{right_scroll}/{right_max_scroll}",
            True,
            MUTED_TEXT,
        )
        screen.blit(scroll_hint, (pad, SCREEN_HEIGHT - 34))

        draw_close_button(screen, fonts, hovered=close_rect.collidepoint(mx, my))
        draw_back_hint(screen, fonts)
        if hovered_card is not None:
            draw_hover_panel(screen, hovered_card, fonts, hovered_card.rect)
        pygame.display.flip()
