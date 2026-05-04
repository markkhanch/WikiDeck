import os
import time

import pygame

from config import (
    BG_DARK,
    BG_MID,
    CARD_HEIGHT,
    CARD_WIDTH,
    GOLD,
    IMAGES_DIR,
    MUTED_TEXT,
    NEON_BLUE,
    NEON_GREEN,
    NEON_RED,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    WHITE_TEXT,
)
from core.card import Card
from core.card_factory import build_card_from_spec
from data.booster import (
    PACK_DISPLAY_NAMES,
    buy_single_card,
    ensure_shop_singles,
    get_pack_types,
    get_pending_packs,
    get_shop_singles,
    open_pack,
    purchase_pack,
)
from data.settings_service import get_bool, target_fps
from ui.components.hover_panel import draw_hover_panel
from ui.screens.common import (
    close_button_rect,
    draw_back_hint,
    draw_background,
    draw_button,
    draw_close_button,
    draw_panel,
    draw_title,
)

TAB_KEYS = ("boosters", "singles", "my_packs")
TAB_LABELS = {
    "boosters": "Booster Packs",
    "singles": "Single Cards",
    "my_packs": "My Packs",
}
PACK_ORDER = ("basic", "premium", "epic", "legendary")
PACK_ACCENT = {
    "basic": (150, 150, 150),
    "premium": (70, 150, 255),
    "epic": (180, 90, 255),
    "legendary": (255, 190, 60),
}


def _prepare_pack_image(surface: pygame.Surface) -> pygame.Surface:
    width, height = surface.get_size()
    cut_x = int(width * 0.14)
    cut_y = int(height * 0.10)
    crop = pygame.Rect(cut_x, cut_y, max(10, width - cut_x * 2), max(10, height - cut_y * 2))
    return surface.subsurface(crop).copy()


def _load_pack_images() -> dict[str, pygame.Surface]:
    images: dict[str, pygame.Surface] = {}
    for pack_type in PACK_ORDER:
        candidates = [
            f"pack_{pack_type}.png",
            f"{pack_type.capitalize()}.png",
            f"{pack_type.upper()}.png",
        ]
        for name in candidates:
            path = os.path.join(IMAGES_DIR, name)
            if os.path.isfile(path):
                try:
                    raw = pygame.image.load(path).convert_alpha()
                    images[pack_type] = _prepare_pack_image(raw)
                except (pygame.error, FileNotFoundError):
                    pass
                break
    return images


def _draw_tab_button(
    screen: pygame.Surface,
    rect: pygame.Rect,
    label: str,
    fonts: dict,
    *,
    active: bool,
    hovered: bool,
) -> None:
    border = NEON_GREEN if active else (NEON_BLUE if hovered else MUTED_TEXT)
    text_color = NEON_GREEN if active else WHITE_TEXT
    pygame.draw.rect(screen, BG_MID, rect)
    pygame.draw.rect(screen, border, rect, width=2)
    text = fonts["small"].render(label, True, text_color)
    screen.blit(text, text.get_rect(center=rect.center))


def run_shop(
    screen: pygame.Surface,
    fonts: dict,
    background: pygame.Surface | None,
) -> str | None:
    clock = pygame.time.Clock()
    pack_images = _load_pack_images()
    ensure_shop_singles(min_count=2)

    active_tab = "boosters"
    pack_counts = {pack_type: 1 for pack_type in PACK_ORDER}
    status_line = ""

    pending_packs: list[dict] = []
    shop_singles: list[dict] = []
    singles_cards_cache: dict[int, Card] = {}
    last_refresh_at = 0.0

    reveal_pack_name = ""
    reveal_cards: list[Card] = []
    reveal_queue: list[dict] = []
    reveal_last_step = 0.0
    tab_rects: dict[str, pygame.Rect] = {}
    pack_controls: dict[str, dict[str, pygame.Rect]] = {}
    single_buy_rects: dict[int, pygame.Rect] = {}
    open_pack_rects: dict[int, pygame.Rect] = {}
    reveal_close_rect = pygame.Rect(0, 0, 0, 0)
    my_packs_scroll = 0
    my_packs_max_scroll = 0

    def refresh_data(force: bool = False) -> None:
        nonlocal pending_packs, shop_singles, singles_cards_cache, last_refresh_at
        now = time.time()
        if not force and now - last_refresh_at < 1.0:
            return
        pending_packs = get_pending_packs()
        shop_singles = get_shop_singles()
        singles_cards_cache = {}
        for row in shop_singles:
            spec = row.get("spec")
            if spec is None:
                continue
            singles_cards_cache[int(row["id"])] = build_card_from_spec(spec)
        last_refresh_at = now

    refresh_data(force=True)

    while True:
        clock.tick(target_fps())
        refresh_data()
        mx, my = pygame.mouse.get_pos()
        now = time.time()

        reveal_step_delay = 0.18 if get_bool("display.animations") else 0.0
        if reveal_queue and now - reveal_last_step >= reveal_step_delay:
            reveal_last_step = now
            reveal_cards.append(build_card_from_spec(reveal_queue.pop(0)))

        close_rect = close_button_rect()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.MOUSEWHEEL and active_tab == "my_packs" and not (reveal_cards or reveal_queue):
                my_packs_scroll = max(0, min(my_packs_max_scroll, my_packs_scroll - event.y * 48))
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if reveal_cards or reveal_queue:
                    reveal_cards.clear()
                    reveal_queue.clear()
                else:
                    return "menu"
            if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
                if active_tab == "my_packs" and not (reveal_cards or reveal_queue):
                    delta = -48 if event.button == 5 else 48
                    my_packs_scroll = max(0, min(my_packs_max_scroll, my_packs_scroll + delta))
                continue
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if reveal_cards or reveal_queue:
                    if reveal_close_rect.collidepoint(mx, my):
                        reveal_cards.clear()
                        reveal_queue.clear()
                    continue

                if close_rect.collidepoint(mx, my):
                    return "menu"
                for key, rect in tab_rects.items():
                    if rect.collidepoint(mx, my):
                        active_tab = key
                        status_line = ""
                        break

                if active_tab == "boosters":
                    for pack_type, controls in pack_controls.items():
                        if controls["minus"].collidepoint(mx, my):
                            pack_counts[pack_type] = max(1, pack_counts[pack_type] - 1)
                        elif controls["plus"].collidepoint(mx, my):
                            pack_counts[pack_type] = min(10, pack_counts[pack_type] + 1)
                        elif controls["buy"].collidepoint(mx, my):
                            amount = pack_counts[pack_type]
                            for _ in range(amount):
                                purchase_pack(pack_type)
                            status_line = f"Purchased {amount}x {PACK_DISPLAY_NAMES[pack_type]}."
                            refresh_data(force=True)

                elif active_tab == "singles":
                    for single_id, rect in single_buy_rects.items():
                        if rect.collidepoint(mx, my):
                            bought = buy_single_card(single_id)
                            if bought is not None:
                                status_line = f"Bought {bought['title']} ({bought['rarity']})."
                                refresh_data(force=True)
                            break

                elif active_tab == "my_packs":
                    for pack_id, rect in open_pack_rects.items():
                        if rect.collidepoint(mx, my):
                            opened_specs = open_pack(pack_id)
                            if opened_specs:
                                row = next((p for p in pending_packs if p["id"] == pack_id), None)
                                reveal_pack_name = row["pack_name"] if row else "Pack"
                                reveal_cards = []
                                reveal_queue = list(opened_specs)
                                reveal_last_step = 0.0
                                status_line = f"Opened {len(opened_specs)} cards."
                                refresh_data(force=True)
                            break

        draw_background(screen, background)
        draw_title(screen, "SHOP", fonts, y=70)

        tab_rects = {}
        pack_controls = {}
        single_buy_rects = {}
        open_pack_rects = {}
        reveal_close_rect = pygame.Rect(0, 0, 0, 0)

        tabs_y = 100
        tab_w = 200
        tab_h = 36
        tab_gap = 10
        tabs_start_x = (SCREEN_WIDTH - (tab_w * len(TAB_KEYS) + tab_gap * (len(TAB_KEYS) - 1))) // 2
        for idx, key in enumerate(TAB_KEYS):
            rect = pygame.Rect(tabs_start_x + idx * (tab_w + tab_gap), tabs_y, tab_w, tab_h)
            tab_rects[key] = rect
            _draw_tab_button(
                screen,
                rect,
                TAB_LABELS[key],
                fonts,
                active=active_tab == key,
                hovered=rect.collidepoint(mx, my),
            )

        content_rect = pygame.Rect(40, 150, SCREEN_WIDTH - 80, SCREEN_HEIGHT - 210)
        draw_panel(screen, content_rect, TAB_LABELS[active_tab], fonts)

        hovered_card: Card | None = None

        if active_tab == "boosters":
            pack_types = get_pack_types()
            card_w = (content_rect.width - 50) // 4
            card_h = content_rect.height - 40
            per_type_latest: dict[str, dict] = {}
            for row in pending_packs:
                per_type_latest.setdefault(row["pack_type"], row)

            for idx, pack_type in enumerate(PACK_ORDER):
                rect = pygame.Rect(content_rect.x + 10 + idx * (card_w + 10), content_rect.y + 24, card_w, card_h)
                pygame.draw.rect(screen, BG_DARK, rect)
                pygame.draw.rect(screen, NEON_BLUE, rect, width=1)

                image = pack_images.get(pack_type)
                art_rect = pygame.Rect(rect.x + 10, rect.y + 10, rect.width - 20, min(170, rect.height - 180))
                pygame.draw.rect(screen, (12, 18, 34), art_rect)
                pygame.draw.rect(screen, PACK_ACCENT.get(pack_type, NEON_BLUE), art_rect, width=1)
                if image is not None:
                    iw, ih = image.get_size()
                    scale = min(art_rect.width / max(1, iw), art_rect.height / max(1, ih))
                    draw_w = max(1, int(iw * scale))
                    draw_h = max(1, int(ih * scale))
                    scaled = pygame.transform.smoothscale(image, (draw_w, draw_h))
                    screen.blit(
                        scaled,
                        (
                            art_rect.x + (art_rect.width - draw_w) // 2,
                            art_rect.y + (art_rect.height - draw_h) // 2,
                        ),
                    )
                else:
                    fallback = fonts["med"].render(PACK_DISPLAY_NAMES[pack_type].split()[0], True, PACK_ACCENT[pack_type])
                    screen.blit(fallback, fallback.get_rect(center=art_rect.center))

                title = fonts["small"].render(PACK_DISPLAY_NAMES[pack_type], True, WHITE_TEXT)
                price = fonts["small"].render(f"{pack_types[pack_type]['price']} gold", True, GOLD)
                screen.blit(title, (rect.x + 10, rect.y + 188))
                screen.blit(price, (rect.x + 10, rect.y + 208))

                minus_rect = pygame.Rect(rect.x + 10, rect.y + 234, 32, 32)
                plus_rect = pygame.Rect(rect.x + rect.width - 42, rect.y + 234, 32, 32)
                qty_rect = pygame.Rect(minus_rect.right + 6, rect.y + 234, rect.width - 96, 32)
                buy_rect = pygame.Rect(rect.x + 10, rect.y + 276, rect.width - 20, 42)
                pack_controls[pack_type] = {"minus": minus_rect, "plus": plus_rect, "buy": buy_rect}

                for btn_rect, txt in ((minus_rect, "-"), (plus_rect, "+")):
                    pygame.draw.rect(screen, BG_MID, btn_rect)
                    pygame.draw.rect(screen, NEON_GREEN if btn_rect.collidepoint(mx, my) else MUTED_TEXT, btn_rect, 2)
                    symbol = fonts["med"].render(txt, True, WHITE_TEXT)
                    screen.blit(symbol, symbol.get_rect(center=btn_rect.center))

                pygame.draw.rect(screen, BG_MID, qty_rect)
                pygame.draw.rect(screen, MUTED_TEXT, qty_rect, 1)
                qty_label = fonts["med"].render(str(pack_counts[pack_type]), True, WHITE_TEXT)
                screen.blit(qty_label, qty_label.get_rect(center=qty_rect.center))

                draw_button(
                    screen,
                    buy_rect,
                    f"Buy {pack_counts[pack_type]} packs",
                    fonts,
                    hovered=buy_rect.collidepoint(mx, my),
                )

                latest = per_type_latest.get(pack_type)
                status_y = buy_rect.bottom + 8
                if latest is None:
                    line = "No active packs"
                elif latest["status"] == "generating":
                    line = f"Generating... {latest['generated_count']}/{latest['pack_size']} cards"
                elif latest["status"] == "error":
                    line = "Generation failed. Buy again."
                elif latest["can_open"]:
                    line = "Open Pack -> My Packs"
                else:
                    line = "Queued..."
                if "Open Pack" in line:
                    status_color = GOLD
                elif latest is not None and latest["status"] == "error":
                    status_color = NEON_RED
                else:
                    status_color = MUTED_TEXT
                status_surf = fonts["small"].render(line, True, status_color)
                screen.blit(status_surf, (rect.x + 10, status_y))

        elif active_tab == "singles":
            left = pygame.Rect(content_rect.x + 20, content_rect.y + 36, 300, content_rect.height - 66)
            right = pygame.Rect(content_rect.x + content_rect.width - 320, content_rect.y + 36, 300, content_rect.height - 66)
            slots = [left, right]

            for idx, slot in enumerate(slots):
                pygame.draw.rect(screen, BG_DARK, slot)
                pygame.draw.rect(screen, NEON_BLUE, slot, 1)
                if idx >= len(shop_singles):
                    empty = fonts["small"].render("Generating new single...", True, MUTED_TEXT)
                    screen.blit(empty, empty.get_rect(center=slot.center))
                    continue

                row = shop_singles[idx]
                card = singles_cards_cache.get(int(row["id"]))
                if card is not None:
                    cx = slot.centerx - CARD_WIDTH // 2
                    cy = slot.y + 16
                    card.set_topleft(cx, cy)
                    card.draw(screen)
                    if card.rect.collidepoint(mx, my):
                        hovered_card = card

                info_y = slot.y + CARD_HEIGHT + 24
                rarity = fonts["small"].render(f"Rarity: {row['rarity']}", True, WHITE_TEXT)
                price = fonts["small"].render(f"Price: {row['price']} gold", True, GOLD)
                screen.blit(rarity, (slot.x + 16, info_y))
                screen.blit(price, (slot.x + 16, info_y + 22))

                buy_rect = pygame.Rect(slot.x + 16, slot.bottom - 54, slot.width - 32, 38)
                single_buy_rects[int(row["id"])] = buy_rect
                draw_button(
                    screen,
                    buy_rect,
                    "Buy Single Card",
                    fonts,
                    hovered=buy_rect.collidepoint(mx, my),
                )

        else:
            row_h = 64
            list_rect = pygame.Rect(content_rect.x + 14, content_rect.y + 34, content_rect.width - 28, content_rect.height - 46)
            pygame.draw.rect(screen, BG_DARK, list_rect)
            pygame.draw.rect(screen, NEON_BLUE, list_rect, 1)
            if not pending_packs:
                msg = fonts["small"].render("No pending packs yet.", True, MUTED_TEXT)
                screen.blit(msg, msg.get_rect(center=list_rect.center))
                my_packs_max_scroll = 0
                my_packs_scroll = 0
            else:
                row_step = row_h + 8
                total_height = len(pending_packs) * row_step
                my_packs_max_scroll = max(0, total_height - list_rect.height + 8)
                my_packs_scroll = max(0, min(my_packs_scroll, my_packs_max_scroll))
                for idx, pack in enumerate(pending_packs):
                    y = list_rect.y + idx * row_step - my_packs_scroll
                    if y + row_h < list_rect.y:
                        continue
                    if y + row_h > list_rect.bottom:
                        break
                    row_rect = pygame.Rect(list_rect.x + 8, y, list_rect.width - 16, row_h)
                    pygame.draw.rect(screen, BG_MID, row_rect)
                    pygame.draw.rect(screen, MUTED_TEXT, row_rect, 1)

                    title = fonts["small"].render(f"#{pack['id']} {pack['pack_name']}", True, WHITE_TEXT)
                    screen.blit(title, (row_rect.x + 10, row_rect.y + 8))

                    if pack["status"] == "generating":
                        state_text = f"Generating... {pack['generated_count']}/{pack['pack_size']} cards"
                        color = MUTED_TEXT
                    elif pack["status"] == "error":
                        state_text = "Generation failed."
                        color = NEON_RED
                    elif pack["can_open"]:
                        state_text = "Open Pack ->"
                        color = NEON_GREEN
                    else:
                        state_text = "Queued..."
                        color = GOLD
                    state = fonts["small"].render(state_text, True, color)
                    screen.blit(state, (row_rect.x + 10, row_rect.y + 34))

                    if pack["can_open"]:
                        btn = pygame.Rect(row_rect.right - 130, row_rect.y + 14, 116, 34)
                        open_pack_rects[int(pack["id"])] = btn
                        draw_button(
                            screen,
                            btn,
                            "Open",
                            fonts,
                            hovered=btn.collidepoint(mx, my),
                        )

                if my_packs_max_scroll > 0:
                    track = pygame.Rect(list_rect.right - 8, list_rect.y + 4, 4, list_rect.height - 8)
                    pygame.draw.rect(screen, (50, 60, 80), track)
                    thumb_h = max(28, int(track.height * (list_rect.height / max(list_rect.height + my_packs_max_scroll, 1))))
                    max_travel = max(1, track.height - thumb_h)
                    thumb_y = track.y + int((my_packs_scroll / max(1, my_packs_max_scroll)) * max_travel)
                    thumb = pygame.Rect(track.x, thumb_y, track.width, thumb_h)
                    pygame.draw.rect(screen, NEON_GREEN, thumb)
                    hint = fonts["small"].render("Mouse wheel to scroll", True, MUTED_TEXT)
                    screen.blit(hint, (list_rect.x + 8, list_rect.bottom - 22))

        gold_label = fonts["small"].render("Gold: ∞ (test mode)", True, GOLD)
        screen.blit(gold_label, (SCREEN_WIDTH - gold_label.get_width() - 16, 120))

        if status_line:
            status = fonts["small"].render(status_line, True, GOLD)
            screen.blit(status, (content_rect.x + 10, SCREEN_HEIGHT - 48))

        if reveal_cards or reveal_queue:
            shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 170))
            screen.blit(shade, (0, 0))

            frame_w = min(SCREEN_WIDTH - 120, CARD_WIDTH * 5 + 140)
            frame_h = min(SCREEN_HEIGHT - 120, CARD_HEIGHT + 150)
            frame = pygame.Rect((SCREEN_WIDTH - frame_w) // 2, (SCREEN_HEIGHT - frame_h) // 2, frame_w, frame_h)
            draw_panel(screen, frame, f"{reveal_pack_name} Opened", fonts)

            reveal_close_rect = pygame.Rect(frame.right - 40, frame.y + 8, 28, 28)
            pygame.draw.rect(screen, BG_MID, reveal_close_rect)
            pygame.draw.rect(
                screen,
                (255, 80, 80) if reveal_close_rect.collidepoint(mx, my) else MUTED_TEXT,
                reveal_close_rect,
                2,
            )
            x_label = fonts["small"].render("X", True, WHITE_TEXT)
            screen.blit(x_label, x_label.get_rect(center=reveal_close_rect.center))

            progress = fonts["small"].render(
                f"Revealed {len(reveal_cards)}/{len(reveal_cards) + len(reveal_queue)} cards",
                True,
                GOLD,
            )
            screen.blit(progress, (frame.x + 14, frame.y + 34))

            if reveal_cards:
                gap = 12
                total_w = len(reveal_cards) * CARD_WIDTH + max(0, len(reveal_cards) - 1) * gap
                start_x = frame.x + (frame.width - total_w) // 2
                y = frame.y + 58
                for idx, card in enumerate(reveal_cards):
                    card.set_topleft(start_x + idx * (CARD_WIDTH + gap), y)
                    card.draw(screen)
                    if card.rect.collidepoint(mx, my):
                        hovered_card = card

        draw_close_button(screen, fonts, hovered=close_rect.collidepoint(mx, my))
        draw_back_hint(screen, fonts)
        if hovered_card is not None:
            draw_hover_panel(screen, hovered_card, fonts, hovered_card.rect)
        pygame.display.flip()
