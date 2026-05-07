import random

import pygame

from config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    BG_DARK,
    BG_MID,
    BG_LIGHT,
    CARD_WIDTH,
    CARD_HEIGHT,
    P1_HAND_CENTER_Y,
    P1_FIELD_CENTER_Y,
    P2_HAND_CENTER_Y,
    P2_FIELD_CENTER_Y,
    FIELD_SPACING,
    P1_FIELD_ZONE,
    P2_FIELD_ZONE,
    DIVIDER_Y,
    END_TURN_BUTTON_RECT,
    NEON_GREEN,
    NEON_BLUE,
    NEON_RED,
    WHITE_TEXT,
    MUTED_TEXT,
    GOLD,
)
from data.settings_service import get_bool, get_int, target_fps
from core.card import Card
from core.player import Player
from core.game_state import GameState, Phase
from network.protocol import (
    CONNECTION_STATUS,
    DISCARD_CARD,
    END_TURN,
    ERROR,
    EVENT,
    GAME_OVER,
    GAME_STATE,
    ORDER_CARD,
    OPPONENT_DISCONNECTED,
    PLAY_CARD,
    ROLE,
    TARGET_SELECT,
    TARGETING,
    YOUR_TURN,
)
from network.sync import apply_serialized_state
from ui.components.hover_panel import draw_hover_panel
from ui.particles import particle_system
from ui.screens.common import draw_close_button, close_button_rect


def _clone_card(c: Card) -> Card:
    clone = Card(
        title=c.title,
        hp=c.hp,
        max_hp=getattr(c, "max_hp", c.hp),
        theme=c.theme,
        rarity=c.rarity,
        epoch=getattr(c, "epoch", "TIMELESS"),
        nemesis=getattr(c, "nemesis", None),
        description=c.description,
        extract=c.extract,
        image=c.image,
        ability_text=c.ability_text,
        ability_trigger=c.ability_trigger,
        effect_type=getattr(c, "effect_type", "NONE"),
        ability_value=int(getattr(c, "ability_value", 0) or 0),
        graveyard_eligible=bool(getattr(c, "graveyard_eligible", False)),
        statuses=set(getattr(c, "statuses", set()) or set()),
        silenced_turns=int(getattr(c, "silenced_turns", 0) or 0),
        on_play=c.on_play,
        on_death=c.on_death,
    )
    return clone


def _make_deck(base_cards: list[Card]) -> list[Card]:
    deck = [_clone_card(c) for c in base_cards]
    random.shuffle(deck)
    return deck


HAND_OVERLAP_STEP = CARD_WIDTH // 2
HAND_MIN_STEP = 20
HAND_SIDE_PADDING = 180
HAND_VISIBLE_SLICE = CARD_HEIGHT // 2
HAND_HOVER_TOP_Y = 16
HAND_HOVER_BOTTOM_Y = SCREEN_HEIGHT - CARD_HEIGHT - 18


def _layout_row(cards: list[Card], center_y: int, spacing: int) -> None:
    n = len(cards)
    if n == 0:
        return
    total_w = n * CARD_WIDTH + (n - 1) * spacing
    start_x = (SCREEN_WIDTH - total_w) // 2
    for i, card in enumerate(cards):
        x = start_x + i * (CARD_WIDTH + spacing)
        card.set_topleft(x, center_y - CARD_HEIGHT // 2)


def _layout_hand_row(cards: list[Card], *, top_side: bool) -> None:
    n = len(cards)
    if n == 0:
        return
    usable_w = max(CARD_WIDTH, SCREEN_WIDTH - HAND_SIDE_PADDING * 2)
    if n == 1:
        step = HAND_OVERLAP_STEP
    else:
        max_step = max(HAND_MIN_STEP, (usable_w - CARD_WIDTH) // (n - 1))
        step = max(HAND_MIN_STEP, min(HAND_OVERLAP_STEP, max_step))
    total_w = CARD_WIDTH + (n - 1) * step
    start_x = (SCREEN_WIDTH - total_w) // 2
    base_y = -CARD_HEIGHT + HAND_VISIBLE_SLICE if top_side else SCREEN_HEIGHT - HAND_VISIBLE_SLICE
    for i, card in enumerate(cards):
        x = start_x + i * step
        card.set_topleft(x, base_y)


def _lift_hovered_hand_card(card: Card, *, top_side: bool) -> None:
    hover_y = HAND_HOVER_TOP_Y if top_side else HAND_HOVER_BOTTOM_Y
    card.set_topleft(card.rect.x, hover_y)


def _relayout(game: GameState) -> None:
    p1, p2 = game.players
    _layout_hand_row(p1.hand, top_side=False)
    _layout_row(p1.on_field, P1_FIELD_CENTER_Y, FIELD_SPACING)
    _layout_hand_row(p2.hand, top_side=True)
    _layout_row(p2.on_field, P2_FIELD_CENTER_Y, FIELD_SPACING)


def _draw_divider(screen: pygame.Surface) -> None:
    pygame.draw.line(screen, NEON_BLUE, (0, DIVIDER_Y), (SCREEN_WIDTH, DIVIDER_Y), width=1)


def _draw_card_back(screen: pygame.Surface, rect: pygame.FRect, fonts: dict) -> None:
    pygame.draw.rect(screen, BG_MID, rect)
    pygame.draw.rect(screen, NEON_BLUE, rect, width=2)
    inner = rect.inflate(-12, -12)
    pygame.draw.rect(screen, BG_LIGHT, inner, width=1)
    logo = fonts["big"].render("W", True, NEON_GREEN)
    screen.blit(logo, logo.get_rect(center=rect.center))


LOG_DRAWER_WIDTH = 390
LOG_DRAWER_HEIGHT = 190
LOG_DRAWER_HANDLE_WIDTH = 32
SIDE_PILE_MARGIN_X = 16
SIDE_PILE_GAP = 12
DECK_MODAL_MARGIN = 40
DECK_MODAL_GRID_GAP = 8


def _action_log_drawer_rect(is_open: bool) -> pygame.Rect:
    open_x = 8
    closed_x = open_x - LOG_DRAWER_WIDTH + LOG_DRAWER_HANDLE_WIDTH
    return pygame.Rect(
        open_x if is_open else closed_x,
        SCREEN_HEIGHT - LOG_DRAWER_HEIGHT - 76,
        LOG_DRAWER_WIDTH,
        LOG_DRAWER_HEIGHT,
    )


def _action_log_handle_rect(drawer_rect: pygame.Rect) -> pygame.Rect:
    return pygame.Rect(
        drawer_rect.right - LOG_DRAWER_HANDLE_WIDTH,
        drawer_rect.y,
        LOG_DRAWER_HANDLE_WIDTH,
        drawer_rect.height,
    )


def _draw_action_log_drawer(
    screen: pygame.Surface,
    game: GameState,
    fonts: dict,
    *,
    is_open: bool,
    mx: int,
    my: int,
) -> tuple[pygame.Rect, pygame.Rect]:
    drawer = _action_log_drawer_rect(is_open)
    handle = _action_log_handle_rect(drawer)
    hovered = handle.collidepoint(mx, my)

    pygame.draw.rect(screen, BG_DARK, drawer)
    pygame.draw.rect(screen, NEON_BLUE, drawer, width=1)
    pygame.draw.rect(screen, BG_MID, handle)
    pygame.draw.rect(screen, NEON_GREEN if hovered else NEON_BLUE, handle, width=2)

    handle_label = "LOG »" if not is_open else "« LOG"
    glyph = fonts["small"].render(handle_label, True, WHITE_TEXT)
    screen.blit(glyph, glyph.get_rect(center=handle.center))

    if is_open:
        title = fonts["small"].render("Action Log", True, GOLD)
        screen.blit(title, (drawer.x + 10, drawer.y + 8))
        lines = game.action_log[-10:]
        for idx, line in enumerate(lines):
            row = fonts["small"].render(f"{idx + 1:>2}. {line}", True, WHITE_TEXT)
            screen.blit(row, (drawer.x + 10, drawer.y + 30 + idx * 15))
        if not lines:
            empty = fonts["small"].render("No actions yet.", True, MUTED_TEXT)
            screen.blit(empty, (drawer.x + 10, drawer.y + 34))
    return drawer, handle


def _draw_card_snapshot(
    screen: pygame.Surface,
    card: Card,
    rect: pygame.Rect,
) -> Card:
    preview = _clone_card(card)
    preview.set_topleft(rect.x, rect.y)
    preview.draw(screen)
    return preview


def _pile_rects(player_idx: int) -> tuple[pygame.Rect, pygame.Rect]:
    center_y = P1_HAND_CENTER_Y if player_idx == 0 else P2_HAND_CENTER_Y
    y = int(center_y - CARD_HEIGHT // 2)
    deck_rect = pygame.Rect(SCREEN_WIDTH - CARD_WIDTH - SIDE_PILE_MARGIN_X, y, CARD_WIDTH, CARD_HEIGHT)
    discard_rect = pygame.Rect(deck_rect.x - CARD_WIDTH - SIDE_PILE_GAP, y, CARD_WIDTH, CARD_HEIGHT)
    return discard_rect, deck_rect


def _can_open_deck_for_player(
    player_idx: int,
    game: GameState,
    *,
    network_mode: bool,
    my_role: str | None,
    can_interact: bool,
) -> bool:
    if not can_interact:
        return False
    local_owner = (not network_mode) or (my_role == "p1" and player_idx == 0) or (my_role == "p2" and player_idx == 1)
    return local_owner and player_idx == game.active_idx


def _shuffled_deck_window_cards(player: Player) -> list[Card]:
    cards = [card for card in player.deck if isinstance(card, Card)]
    random.shuffle(cards)
    return cards


def _deck_modal_rect() -> pygame.Rect:
    return pygame.Rect(
        DECK_MODAL_MARGIN,
        DECK_MODAL_MARGIN + 18,
        SCREEN_WIDTH - DECK_MODAL_MARGIN * 2,
        SCREEN_HEIGHT - DECK_MODAL_MARGIN * 2 - 36,
    )


def _deck_modal_close_rect(panel: pygame.Rect) -> pygame.Rect:
    return pygame.Rect(panel.right - 42, panel.y + 10, 30, 30)


def _draw_deck_modal(
    screen: pygame.Surface,
    fonts: dict,
    owner: Player,
    cards: list[Card],
    *,
    mx: int,
    my: int,
) -> tuple[pygame.Rect, pygame.Rect, Card | None, pygame.FRect | None]:
    shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 165))
    screen.blit(shade, (0, 0))

    panel = _deck_modal_rect()
    pygame.draw.rect(screen, BG_DARK, panel)
    pygame.draw.rect(screen, NEON_BLUE, panel, width=2)

    close_rect = _deck_modal_close_rect(panel)
    hovered_close = close_rect.collidepoint(mx, my)
    pygame.draw.rect(screen, BG_MID, close_rect)
    pygame.draw.rect(screen, NEON_RED if hovered_close else MUTED_TEXT, close_rect, width=2)
    close_text = fonts["med"].render("X", True, NEON_RED if hovered_close else WHITE_TEXT)
    screen.blit(close_text, close_text.get_rect(center=close_rect.center))

    header = fonts["med"].render(f"{owner.name} Deck ({len(cards)})", True, GOLD)
    screen.blit(header, (panel.x + 14, panel.y + 12))
    note = fonts["small"].render("Deck view is randomized. Draws are random too.", True, MUTED_TEXT)
    screen.blit(note, (panel.x + 14, panel.y + 40))

    hovered_card: Card | None = None
    hovered_anchor: pygame.FRect | None = None
    if not cards:
        empty = fonts["med"].render("Deck is empty.", True, MUTED_TEXT)
        screen.blit(empty, empty.get_rect(center=panel.center))
        return panel, close_rect, None, None

    grid_left = panel.x + 12
    grid_top = panel.y + 66
    grid_w = panel.width - 24
    grid_h = panel.height - 80
    cols = max(1, min(10, (grid_w + DECK_MODAL_GRID_GAP) // (CARD_WIDTH + DECK_MODAL_GRID_GAP)))
    rows = max(1, (grid_h + DECK_MODAL_GRID_GAP) // (CARD_HEIGHT + DECK_MODAL_GRID_GAP))
    max_cards = cols * rows

    for idx, card in enumerate(cards[:max_cards]):
        col = idx % cols
        row = idx // cols
        x = grid_left + col * (CARD_WIDTH + DECK_MODAL_GRID_GAP)
        y = grid_top + row * (CARD_HEIGHT + DECK_MODAL_GRID_GAP)
        preview = _draw_card_snapshot(screen, card, pygame.Rect(x, y, CARD_WIDTH, CARD_HEIGHT))
        if preview.rect.collidepoint(mx, my):
            hovered_card = preview
            hovered_anchor = preview.rect

    if len(cards) > max_cards:
        more = fonts["small"].render(f"+ {len(cards) - max_cards} more cards", True, MUTED_TEXT)
        screen.blit(more, (panel.right - more.get_width() - 14, panel.bottom - 18))
    return panel, close_rect, hovered_card, hovered_anchor


def _ordered_discard_window_cards(player: Player) -> list[Card]:
    return [card for card in player.discard if isinstance(card, Card)]


def _discard_modal_rect() -> pygame.Rect:
    return pygame.Rect(
        DECK_MODAL_MARGIN,
        DECK_MODAL_MARGIN + 18,
        SCREEN_WIDTH - DECK_MODAL_MARGIN * 2,
        SCREEN_HEIGHT - DECK_MODAL_MARGIN * 2 - 36,
    )


def _discard_modal_close_rect(panel: pygame.Rect) -> pygame.Rect:
    return pygame.Rect(panel.right - 42, panel.y + 10, 30, 30)


def _draw_discard_modal(
    screen: pygame.Surface,
    fonts: dict,
    owner: Player,
    cards: list[Card],
    *,
    mx: int,
    my: int,
) -> tuple[pygame.Rect, pygame.Rect, Card | None, pygame.FRect | None]:
    shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 165))
    screen.blit(shade, (0, 0))

    panel = _discard_modal_rect()
    pygame.draw.rect(screen, BG_DARK, panel)
    pygame.draw.rect(screen, NEON_BLUE, panel, width=2)

    close_rect = _discard_modal_close_rect(panel)
    hovered_close = close_rect.collidepoint(mx, my)
    pygame.draw.rect(screen, BG_MID, close_rect)
    pygame.draw.rect(screen, NEON_RED if hovered_close else MUTED_TEXT, close_rect, width=2)
    close_text = fonts["med"].render("X", True, NEON_RED if hovered_close else WHITE_TEXT)
    screen.blit(close_text, close_text.get_rect(center=close_rect.center))

    header = fonts["med"].render(f"{owner.name} Discard Pile ({len(cards)})", True, GOLD)
    screen.blit(header, (panel.x + 14, panel.y + 12))
    note = fonts["small"].render("Cards are shown in discard order.", True, MUTED_TEXT)
    screen.blit(note, (panel.x + 14, panel.y + 40))

    hovered_card: Card | None = None
    hovered_anchor: pygame.FRect | None = None
    if not cards:
        empty = fonts["med"].render("Discard pile is empty.", True, MUTED_TEXT)
        screen.blit(empty, empty.get_rect(center=panel.center))
        return panel, close_rect, None, None

    grid_left = panel.x + 12
    grid_top = panel.y + 66
    grid_w = panel.width - 24
    grid_h = panel.height - 80
    cols = max(1, min(10, (grid_w + DECK_MODAL_GRID_GAP) // (CARD_WIDTH + DECK_MODAL_GRID_GAP)))
    rows = max(1, (grid_h + DECK_MODAL_GRID_GAP) // (CARD_HEIGHT + DECK_MODAL_GRID_GAP))
    max_cards = cols * rows

    for idx, card in enumerate(cards[:max_cards]):
        col = idx % cols
        row = idx // cols
        x = grid_left + col * (CARD_WIDTH + DECK_MODAL_GRID_GAP)
        y = grid_top + row * (CARD_HEIGHT + DECK_MODAL_GRID_GAP)
        preview = _draw_card_snapshot(screen, card, pygame.Rect(x, y, CARD_WIDTH, CARD_HEIGHT))
        if preview.rect.collidepoint(mx, my):
            hovered_card = preview
            hovered_anchor = preview.rect

    if len(cards) > max_cards:
        more = fonts["small"].render(f"+ {len(cards) - max_cards} more cards", True, MUTED_TEXT)
        screen.blit(more, (panel.right - more.get_width() - 14, panel.bottom - 18))
    return panel, close_rect, hovered_card, hovered_anchor


def _draw_side_piles(
    screen: pygame.Surface,
    game: GameState,
    fonts: dict,
    *,
    network_mode: bool,
    my_role: str | None,
    can_interact: bool,
    mx: int,
    my: int,
) -> tuple[Card | None, pygame.FRect | None]:
    hovered_card: Card | None = None
    hovered_anchor: pygame.FRect | None = None

    for idx, player in enumerate(game.players):
        discard_rect, deck_rect = _pile_rects(idx)
        can_open_deck = _can_open_deck_for_player(
            idx,
            game,
            network_mode=network_mode,
            my_role=my_role,
            can_interact=can_interact,
        )

        pygame.draw.rect(screen, BG_MID, discard_rect)
        pygame.draw.rect(screen, NEON_RED, discard_rect, width=1)
        if player.discard:
            top_discard = _draw_card_snapshot(screen, player.discard[-1], discard_rect)
            if discard_rect.collidepoint(mx, my):
                hovered_card = top_discard
                hovered_anchor = top_discard.rect
        else:
            _draw_card_back(screen, discard_rect, fonts)
        discard_label = fonts["small"].render(f"Discard {len(player.discard)}", True, NEON_RED)
        screen.blit(discard_label, (discard_rect.x, discard_rect.y - 16 if idx == 0 else discard_rect.bottom + 2))

        pygame.draw.rect(screen, BG_MID, deck_rect)
        pygame.draw.rect(screen, NEON_BLUE, deck_rect, width=1)
        _draw_card_back(screen, deck_rect, fonts)
        deck_label_color = NEON_GREEN if can_open_deck else NEON_BLUE
        label = f"Deck {len(player.deck)}"
        if can_open_deck:
            label += " (click)"
        deck_label = fonts["small"].render(label, True, deck_label_color)
        screen.blit(deck_label, (deck_rect.x + 6, deck_rect.y - 16 if idx == 0 else deck_rect.bottom + 2))

    return hovered_card, hovered_anchor


def _wrap_text(text: str, font: pygame.font.Font, max_w: int) -> list[str]:
    if max_w <= 0:
        return [text]
    lines: list[str] = []
    for paragraph in str(text or "").split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        line = words[0]
        for word in words[1:]:
            probe = f"{line} {word}"
            if font.size(probe)[0] <= max_w:
                line = probe
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def _is_hand_face_up(
    player_idx: int,
    game: GameState,
    *,
    network_mode: bool,
    my_role: str | None,
) -> bool:
    if network_mode:
        return (my_role == "p1" and player_idx == 0) or (my_role == "p2" and player_idx == 1)
    return player_idx == game.active_idx


def _apply_hand_hover_pose(
    game: GameState,
    *,
    network_mode: bool,
    my_role: str | None,
    mx: int,
    my: int,
    allow_hover: bool,
) -> dict[int, Card]:
    hovered: dict[int, Card] = {}
    if not allow_hover:
        return hovered
    for idx, player in enumerate(game.players):
        if not _is_hand_face_up(idx, game, network_mode=network_mode, my_role=my_role):
            continue
        for card in reversed(player.hand):
            if not card.rect.collidepoint(mx, my):
                continue
            _lift_hovered_hand_card(card, top_side=(idx == 1))
            hovered[idx] = card
            break
    return hovered


def _ability_preview_lines(card: Card) -> list[str]:
    trigger = str(getattr(card, "ability_trigger", "") or "").strip().upper()
    ability_text = str(getattr(card, "ability_text", "") or "").strip()
    if ability_text:
        if trigger:
            return [f"{trigger}: {ability_text}"]
        return [ability_text]
    effect_type = str(getattr(card, "effect_type", "NONE") or "NONE").strip().upper()
    if effect_type and effect_type != "NONE":
        value = int(getattr(card, "ability_value", 0) or 0)
        return [f"ABILITY: {effect_type} {value:+d}" if value else f"ABILITY: {effect_type}"]
    return ["No active ability text."]


def _draw_hand_ability_hint(
    screen: pygame.Surface,
    fonts: dict,
    card: Card,
) -> None:
    panel_w = 320
    pad = 10
    title_font = fonts.get("med", fonts["small"])
    body_font = fonts["small"]
    lines = []
    for src in _ability_preview_lines(card):
        lines.extend(_wrap_text(src, body_font, panel_w - pad * 2))
    panel_h = min(170, 44 + len(lines) * (body_font.get_height() + 2))
    px = int(card.rect.right + 12)
    if px + panel_w > SCREEN_WIDTH - 8:
        px = int(card.rect.left - panel_w - 12)
    px = max(8, min(px, SCREEN_WIDTH - panel_w - 8))
    py = int(card.rect.top - 8)
    py = max(8, min(py, SCREEN_HEIGHT - panel_h - 8))

    panel = pygame.Rect(px, py, panel_w, panel_h)
    pygame.draw.rect(screen, BG_DARK, panel)
    pygame.draw.rect(screen, NEON_BLUE, panel, width=2)

    cx = panel.x + pad
    cy = panel.y + pad
    title = title_font.render(card.title[:28], True, WHITE_TEXT)
    screen.blit(title, (cx, cy))
    cy += title.get_height() + 4
    for line in lines:
        surf = body_font.render(line, True, GOLD)
        screen.blit(surf, (cx, cy))
        cy += body_font.get_height() + 2
        if cy > panel.bottom - 22:
            break
    hint = body_font.render("RMB: full details", True, MUTED_TEXT)
    screen.blit(hint, (cx, panel.bottom - hint.get_height() - 6))


def _blit_cover_image(surface: pygame.Surface, image: pygame.Surface, rect: pygame.Rect) -> None:
    iw, ih = image.get_size()
    if iw <= 0 or ih <= 0:
        return
    scale = max(rect.width / iw, rect.height / ih)
    new_w = max(1, int(iw * scale))
    new_h = max(1, int(ih * scale))
    scaled = pygame.transform.smoothscale(image, (new_w, new_h))
    dx = (rect.width - new_w) // 2
    dy = (rect.height - new_h) // 2
    clip = pygame.Surface(rect.size, pygame.SRCALPHA)
    clip.blit(scaled, (dx, dy))
    surface.blit(clip, rect.topleft)


def _detail_modal_rect() -> pygame.Rect:
    margin_x = 56
    margin_y = 52
    return pygame.Rect(margin_x, margin_y, SCREEN_WIDTH - margin_x * 2, SCREEN_HEIGHT - margin_y * 2)


def _detail_modal_close_rect(panel: pygame.Rect) -> pygame.Rect:
    return pygame.Rect(panel.right - 42, panel.y + 10, 30, 30)


def _draw_detail_modal(
    screen: pygame.Surface,
    fonts: dict,
    card: Card,
    *,
    mx: int,
    my: int,
) -> tuple[pygame.Rect, pygame.Rect]:
    shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 188))
    screen.blit(shade, (0, 0))

    panel = _detail_modal_rect()
    pygame.draw.rect(screen, BG_DARK, panel)
    pygame.draw.rect(screen, GOLD, panel, width=2)

    close_rect = _detail_modal_close_rect(panel)
    hovered_close = close_rect.collidepoint(mx, my)
    pygame.draw.rect(screen, BG_MID, close_rect)
    pygame.draw.rect(screen, NEON_RED if hovered_close else MUTED_TEXT, close_rect, width=2)
    close_text = fonts["med"].render("X", True, NEON_RED if hovered_close else WHITE_TEXT)
    screen.blit(close_text, close_text.get_rect(center=close_rect.center))

    art_w = int(panel.width * 0.33)
    art_rect = pygame.Rect(panel.x + 16, panel.y + 16, art_w, panel.height - 32)
    pygame.draw.rect(screen, BG_MID, art_rect)
    pygame.draw.rect(screen, NEON_BLUE, art_rect, width=2)
    inner = art_rect.inflate(-4, -4)
    if card.image is not None:
        _blit_cover_image(screen, card.image, inner)
    else:
        pygame.draw.rect(screen, BG_LIGHT, inner)
        fallback = fonts["big"].render((card.title[:1] or "?").upper(), True, WHITE_TEXT)
        screen.blit(fallback, fallback.get_rect(center=inner.center))

    top_badge = pygame.Surface((inner.width, 28), pygame.SRCALPHA)
    top_badge.fill((0, 0, 0, 150))
    screen.blit(top_badge, inner.topleft)
    hp_rect = pygame.Rect(inner.x + 6, inner.y + 4, 44, 20)
    pygame.draw.rect(screen, BG_DARK, hp_rect)
    pygame.draw.rect(screen, NEON_RED, hp_rect, width=1)
    hp_text = fonts["small"].render(f"HP {card.hp}", True, NEON_RED)
    screen.blit(hp_text, hp_text.get_rect(center=hp_rect.center))

    tx = art_rect.right + 16
    tw = panel.right - tx - 16
    ty = panel.y + 16
    title_font = fonts.get("panel_title") or fonts["med"]
    body_font = fonts["small"]
    for line in _wrap_text(card.title, title_font, tw):
        surf = title_font.render(line, True, WHITE_TEXT)
        screen.blit(surf, (tx, ty))
        ty += surf.get_height() + 2
    meta = body_font.render(f"{card.theme} • {card.rarity}", True, MUTED_TEXT)
    screen.blit(meta, (tx, ty))
    ty += meta.get_height() + 8

    ability_header = body_font.render("Ability", True, GOLD)
    screen.blit(ability_header, (tx, ty))
    ty += ability_header.get_height() + 2
    for src in _ability_preview_lines(card):
        for line in _wrap_text(src, body_font, tw):
            surf = body_font.render(line, True, WHITE_TEXT)
            screen.blit(surf, (tx, ty))
            ty += body_font.get_height() + 1
    ty += 8

    if card.description:
        desc_header = body_font.render("Description", True, GOLD)
        screen.blit(desc_header, (tx, ty))
        ty += desc_header.get_height() + 2
        for line in _wrap_text(card.description, body_font, tw):
            surf = body_font.render(line, True, MUTED_TEXT)
            screen.blit(surf, (tx, ty))
            ty += body_font.get_height() + 1
        ty += 8

    if card.extract:
        lore_header = body_font.render("Details", True, GOLD)
        screen.blit(lore_header, (tx, ty))
        ty += lore_header.get_height() + 2
        max_lines = max(0, (panel.bottom - 18 - ty) // (body_font.get_height() + 1))
        for line in _wrap_text(card.extract, body_font, tw)[:max_lines]:
            surf = body_font.render(line, True, WHITE_TEXT)
            screen.blit(surf, (tx, ty))
            ty += body_font.get_height() + 1

    footer = body_font.render("ESC / click outside to close", True, MUTED_TEXT)
    screen.blit(footer, (panel.right - footer.get_width() - 14, panel.bottom - footer.get_height() - 8))
    return panel, close_rect


def _draw_hud(screen: pygame.Surface, game: GameState, fonts: dict) -> None:
    p1, p2 = game.players
    active = game.active_player

    center_text = f"Turn {game.turn_number}  —  {active.name}'s turn ({game.phase.value})"
    surf = fonts["hud"].render(center_text, True, NEON_GREEN)
    screen.blit(surf, surf.get_rect(midtop=(SCREEN_WIDTH // 2, 4)))

    if game.last_event:
        ev = fonts["small"].render(game.last_event, True, GOLD)
        screen.blit(ev, ev.get_rect(midtop=(SCREEN_WIDTH // 2, 26)))

    def _draw_score_chip(label: str, value: str, x: int, y: int, border: tuple[int, int, int]) -> int:
        text = fonts["small"].render(f"{label} {value}", True, WHITE_TEXT)
        rect = pygame.Rect(x, y, text.get_width() + 12, text.get_height() + 4)
        pygame.draw.rect(screen, BG_MID, rect)
        pygame.draw.rect(screen, border, rect, width=1)
        screen.blit(text, (rect.x + 6, rect.y + 2))
        return rect.right + 6

    def _draw_player_stats(p: Player, meta_y: int, score_y: int, color: tuple[int, int, int]) -> None:
        field_hp = game.base_sum(p)
        score = game.score_for(p)
        line = f"{p.name}  H:{len(p.hand)}  D:{len(p.deck)}  X:{len(p.discard)}  F:{len(p.on_field)}"
        screen.blit(fonts["small"].render(line, True, color), (10, meta_y))
        x = 10
        x = _draw_score_chip("FIELD HP", str(field_hp), x, score_y, NEON_BLUE)
        x = _draw_score_chip("TOTAL", str(score), x, score_y, NEON_GREEN)

    _draw_player_stats(p2, 4, 22, NEON_GREEN if active is p2 else MUTED_TEXT)
    _draw_player_stats(p1, SCREEN_HEIGHT - 42, SCREEN_HEIGHT - 24, NEON_GREEN if active is p1 else MUTED_TEXT)


def _draw_end_turn_button(screen: pygame.Surface, rect: pygame.Rect,
                          enabled: bool, fonts: dict) -> None:
    color = NEON_GREEN if enabled else MUTED_TEXT
    pygame.draw.rect(screen, BG_MID, rect)
    pygame.draw.rect(screen, color, rect, width=2)
    text = fonts["med"].render("End Turn", True, color)
    screen.blit(text, text.get_rect(center=rect.center))


def _draw_game_over(screen: pygame.Surface, game: GameState, fonts: dict) -> None:
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 190))
    screen.blit(overlay, (0, 0))

    p1, p2 = game.players
    s1, s2 = game.score_for(p1), game.score_for(p2)

    title = fonts["big"].render("MATCH OVER", True, NEON_GREEN)
    screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 240)))

    score_text = f"{p1.name}: {s1}      {p2.name}: {s2}"
    score_surf = fonts["med"].render(score_text, True, WHITE_TEXT)
    screen.blit(score_surf, score_surf.get_rect(center=(SCREEN_WIDTH // 2, 320)))

    if s1 > s2:
        msg = f"{p1.name} wins!"
    elif s2 > s1:
        msg = f"{p2.name} wins!"
    else:
        msg = "Draw"
    win_surf = fonts["med"].render(msg, True, GOLD)
    screen.blit(win_surf, win_surf.get_rect(center=(SCREEN_WIDTH // 2, 370)))

    hint = fonts["small"].render("Press Esc to return to menu", True, MUTED_TEXT)
    screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, 440)))


def _targeting_cancel_rect() -> pygame.Rect:
    return pygame.Rect((SCREEN_WIDTH - 160) // 2, SCREEN_HEIGHT - 54, 160, 36)


def _layout_discard_targets(game: GameState) -> None:
    state = game.targeting_state
    if not state.get("active") or state.get("target_side") != "discard":
        return
    valid_targets = list(state.get("valid_targets", []))
    if not valid_targets:
        return
    cols = min(5, max(1, len(valid_targets)))
    gap = 12
    rows = (len(valid_targets) + cols - 1) // cols
    total_w = cols * CARD_WIDTH + (cols - 1) * gap
    total_h = rows * CARD_HEIGHT + (rows - 1) * gap
    start_x = (SCREEN_WIDTH - total_w) // 2
    start_y = (SCREEN_HEIGHT - total_h) // 2 + 10
    for idx, card in enumerate(valid_targets):
        col = idx % cols
        row = idx // cols
        card.set_topleft(start_x + col * (CARD_WIDTH + gap), start_y + row * (CARD_HEIGHT + gap))


def _draw_targeting_overlay(screen: pygame.Surface, game: GameState, fonts: dict) -> None:
    if not game.is_targeting_active():
        return
    state = game.targeting_state
    target_side = str(state.get("target_side") or "")
    valid_targets = list(state.get("valid_targets", []))

    shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 145))
    screen.blit(shade, (0, 0))

    color = NEON_BLUE
    if target_side == "enemy":
        color = NEON_RED
    elif target_side == "friendly":
        color = NEON_GREEN

    if target_side == "discard":
        panel_w = min(SCREEN_WIDTH - 120, 900)
        panel_h = min(SCREEN_HEIGHT - 180, 440)
        panel = pygame.Rect((SCREEN_WIDTH - panel_w) // 2, (SCREEN_HEIGHT - panel_h) // 2, panel_w, panel_h)
        pygame.draw.rect(screen, BG_DARK, panel)
        pygame.draw.rect(screen, NEON_BLUE, panel, width=2)
        for card in valid_targets:
            card.draw(screen)
            pygame.draw.rect(screen, color, card.rect, width=3)
    else:
        for card in valid_targets:
            pygame.draw.rect(screen, color, card.rect, width=3)

    prompt = str(state.get("prompt") or f"Select a target for {state.get('effect_type', '')}")
    text = fonts["med"].render(prompt, True, WHITE_TEXT)
    screen.blit(text, text.get_rect(center=(SCREEN_WIDTH // 2, 52)))

    cancel_rect = _targeting_cancel_rect()
    pygame.draw.rect(screen, BG_MID, cancel_rect)
    pygame.draw.rect(screen, NEON_RED, cancel_rect, width=2)
    cancel_text = fonts["med"].render("Cancel", True, WHITE_TEXT)
    screen.blit(cancel_text, cancel_text.get_rect(center=cancel_rect.center))


def _player_for_role(game: GameState, role: str | None) -> Player | None:
    if role == "p1":
        return game.players[0]
    if role == "p2":
        return game.players[1]
    return None


def _owner_key_for_card(game: GameState, card: Card) -> str | None:
    for idx, player in enumerate(game.players):
        if card in player.hand or card in player.on_field or card in player.discard:
            return "p1" if idx == 0 else "p2"
    return None


def _fallback_event_rect() -> pygame.Rect:
    rect = pygame.Rect(0, 0, 2, 2)
    rect.center = (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
    return rect


def _event_rects_for_text(game: GameState, event_text: str) -> tuple[pygame.Rect, pygame.Rect | None]:
    text = str(event_text or "").strip().lower()
    if not text:
        return _fallback_event_rect(), None

    matches: list[pygame.Rect] = []
    seen_titles: set[str] = set()
    for player in game.players:
        for zone in (player.on_field, player.hand, player.discard):
            for card in zone:
                title = str(getattr(card, "title", "") or "").strip()
                if not title:
                    continue
                title_key = title.lower()
                if title_key in seen_titles or title_key not in text:
                    continue
                seen_titles.add(title_key)
                matches.append(card.rect)

    if matches:
        source_rect = matches[0]
        target_rect = matches[1] if len(matches) > 1 else None
        return source_rect, target_rect

    active = game.active_player
    if active.on_field:
        return active.on_field[0].rect, None
    if active.hand:
        return active.hand[0].rect, None
    return _fallback_event_rect(), None


def _emit_particles_for_event(event_text, source_rect, target_rect=None):
    cx = source_rect.centerx
    cy = source_rect.centery
    tx = target_rect.centerx if target_rect else None
    ty = target_rect.centery if target_rect else None
    text = str(event_text or "").upper()
    for keyword in [
        "DAMAGE",
        "BLEEDING",
        "VITALITY",
        "SHIELD",
        "POISON",
        "DESTROY",
        "BANISH",
        "DEPLOY",
        "DEATHWISH",
        "GOLD",
        "DRAW",
        "DUEL",
        "CLASH",
        "LOCK",
        "HEAL",
        "REVIVE",
        "TIMER",
    ]:
        if keyword in text:
            particle_system.trigger(keyword, cx, cy, tx, ty)
            break


def _install_particle_log_hook(game: GameState) -> None:
    original_log_event = game.log_event

    def _log_event_with_particles(message: str) -> None:
        clean = (message or "").strip()
        original_log_event(message)
        if not clean:
            return
        source_rect, target_rect = _event_rects_for_text(game, clean)
        _emit_particles_for_event(clean, source_rect, target_rect)

    game.log_event = _log_event_with_particles  # type: ignore[method-assign]


def _append_network_event(game: GameState, text: str) -> None:
    clean = (text or "").strip()
    if not clean:
        return
    game.log_event(clean)


def _consume_network_messages(
    game: GameState,
    network_client,
    my_role: str | None,
    status_line: str,
    has_received_state: bool,
) -> tuple[str | None, str, bool, bool, bool]:
    state_changed = False
    disconnected = False
    for msg in network_client.poll():
        msg_type = str(msg.get("type", ""))
        data = dict(msg.get("data", {}))
        if msg_type == ROLE:
            role = str(data.get("role", "") or "")
            my_role = role or my_role
            if my_role:
                status_line = f"Connected as {my_role.upper()}."
        elif msg_type == GAME_STATE:
            try:
                apply_serialized_state(game, data)
            except Exception as e:
                print(f"[net] bad state packet: {e}")
                return my_role, status_line, state_changed, disconnected, has_received_state
            game.debug("RX game_state applied to local GameState.", include_state=True)
            state_changed = True
            first_state = not has_received_state
            has_received_state = True
            active_player = str(data.get("active_player", "") or "").lower()
            if my_role and active_player in {"p1", "p2"}:
                network_client.is_my_turn = active_player == my_role
            if first_state and status_line.strip().lower() == "waiting for server...":
                status_line = "State synchronized."
        elif msg_type == YOUR_TURN:
            player = str(data.get("player", "") or "")
            if player and my_role:
                network_client.is_my_turn = player == my_role
                status_line = "Your turn." if network_client.is_my_turn else "Opponent turn..."
            elif player:
                network_client.is_my_turn = False
                status_line = "Turn updated."
        elif msg_type == TARGETING:
            prompt = str(data.get("prompt", "") or "")
            if prompt:
                status_line = prompt
        elif msg_type == EVENT:
            _append_network_event(game, str(data.get("text", "") or ""))
        elif msg_type == ERROR:
            status_line = str(data.get("text", "Network error") or "Network error")
            if "connection closed" in status_line.lower():
                disconnected = True
        elif msg_type == CONNECTION_STATUS:
            state = str(data.get("status", "") or "")
            if state == "connected":
                host = data.get("host")
                port = data.get("port")
                status_line = f"Connected to {host}:{port}"
            elif state == "failed":
                status_line = str(data.get("error", "Connection failed"))
                network_client.is_my_turn = False
                disconnected = True
            elif state == "closed":
                status_line = "Connection closed."
                network_client.is_my_turn = False
                disconnected = True
        elif msg_type == OPPONENT_DISCONNECTED:
            status_line = "Opponent disconnected."
            disconnected = True
        elif msg_type == GAME_OVER:
            winner = str(data.get("winner", "draw"))
            if winner == "draw":
                status_line = "Game over: draw"
            else:
                status_line = f"Game over: {winner.upper()} wins"
    return my_role, status_line, state_changed, disconnected, has_received_state


def _draw_network_status(
    screen: pygame.Surface,
    fonts: dict,
    my_role: str | None,
    is_my_turn: bool,
    status_line: str,
) -> None:
    role_text = f"Role: {my_role.upper()}" if my_role else "Role: ?"
    turn_text = "Your turn" if is_my_turn else "Opponent turn"
    left = fonts["small"].render(f"{role_text} | {turn_text}", True, NEON_BLUE)
    x = SCREEN_WIDTH - max(360, left.get_width() + 16)
    screen.blit(left, (x, 46))
    if status_line:
        right = fonts["small"].render(status_line, True, GOLD)
        screen.blit(right, (x, 64))


def run_match(
    screen: pygame.Surface,
    fonts: dict,
    background: pygame.Surface | None,
    base_cards: list[Card],
    network_client=None,
    network_role: str | None = None,
) -> str | None:
    clock = pygame.time.Clock()
    network_mode = network_client is not None

    if network_mode:
        p1 = Player(name="P1", deck=[])
        p2 = Player(name="P2", deck=[])
        game = GameState(
            players=[p1, p2],
            active_idx=0,
            verbose_terminal_logs=get_bool("debug.match_verbose_logs"),
        )
        game.phase = Phase.MAIN
        game.debug("Network match screen initialized; waiting for server state.", include_state=True)
    else:
        p1 = Player(name="P1", deck=_make_deck(base_cards))
        p2 = Player(name="P2", deck=_make_deck(base_cards))
        hand_size = get_int("gameplay.starting_hand_size")
        p1.draw_starting_hand(hand_size)
        p2.draw_starting_hand(hand_size)
        game = GameState(
            players=[p1, p2],
            active_idx=0,
            verbose_terminal_logs=get_bool("debug.match_verbose_logs"),
        )
        game.start_match()
        game.debug("Match screen initialized and first turn started.", include_state=True)
    _relayout(game)
    _install_particle_log_hook(game)
    particle_system.particles.clear()
    particle_system.shockwaves.clear()
    particle_system.lightnings.clear()

    p1_field_zone = pygame.Rect(*P1_FIELD_ZONE)
    p2_field_zone = pygame.Rect(*P2_FIELD_ZONE)
    end_turn_rect = pygame.Rect(*END_TURN_BUTTON_RECT)

    dragging_card: Card | None = None
    drag_offset = (0.0, 0.0)
    my_role = network_role
    network_status = "Waiting for server..."
    has_received_state = False
    log_drawer_open = False
    deck_modal_open = False
    deck_modal_owner_idx: int | None = None
    deck_modal_cards: list[Card] = []
    discard_modal_open = False
    discard_modal_owner_idx: int | None = None
    discard_modal_cards: list[Card] = []
    detail_modal_open = False
    detail_modal_card: Card | None = None
    if network_mode and network_client is not None:
        network_client.is_my_turn = False

    while True:
        clock.tick(target_fps())
        if network_mode and network_client is not None:
            my_role, network_status, state_changed, disconnected, has_received_state = _consume_network_messages(
                game,
                network_client,
                my_role,
                network_status,
                has_received_state,
            )
            if disconnected:
                return "menu"
            if state_changed:
                dragging_card = None
                _relayout(game)
                if deck_modal_open and deck_modal_owner_idx in {0, 1}:
                    deck_modal_cards = _shuffled_deck_window_cards(game.players[deck_modal_owner_idx])
                if discard_modal_open and discard_modal_owner_idx in {0, 1}:
                    discard_modal_cards = _ordered_discard_window_cards(game.players[discard_modal_owner_idx])

        active = game.active_player
        my_player = _player_for_role(game, my_role) if network_mode else active
        controlling_player = my_player if my_player is not None else active
        is_my_turn = (not network_mode) or bool(getattr(network_client, "is_my_turn", False))
        can_interact = (not network_mode) or (my_player is not None and is_my_turn)
        if deck_modal_open and (
            deck_modal_owner_idx is None
            or not _can_open_deck_for_player(
                deck_modal_owner_idx,
                game,
                network_mode=network_mode,
                my_role=my_role,
                can_interact=can_interact,
            )
        ):
            deck_modal_open = False
            deck_modal_owner_idx = None
            deck_modal_cards = []
        if discard_modal_open and discard_modal_owner_idx is None:
            discard_modal_open = False
            discard_modal_owner_idx = None
            discard_modal_cards = []
        if detail_modal_open and detail_modal_card is None:
            detail_modal_open = False
        if my_role == "p1":
            my_field_zone = p1_field_zone
        elif my_role == "p2":
            my_field_zone = p2_field_zone
        else:
            my_field_zone = p1_field_zone if game.active_idx == 0 else p2_field_zone
        active_field_zone = my_field_zone if network_mode else (p1_field_zone if game.active_idx == 0 else p2_field_zone)
        mx, my = pygame.mouse.get_pos()
        close_rect = close_button_rect()
        log_drawer_rect = _action_log_drawer_rect(log_drawer_open)
        log_drawer_handle_rect = _action_log_handle_rect(log_drawer_rect)
        if dragging_card is None:
            _relayout(game)
        allow_hover_pose = (
            dragging_card is None
            and not game.is_targeting_active()
            and not deck_modal_open
            and not discard_modal_open
            and not detail_modal_open
        )
        hovered_hand_cards = _apply_hand_hover_pose(
            game,
            network_mode=network_mode,
            my_role=my_role,
            mx=mx,
            my=my,
            allow_hover=allow_hover_pose,
        )
        _layout_discard_targets(game)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if detail_modal_open:
                    detail_modal_open = False
                    detail_modal_card = None
                    continue
                if deck_modal_open:
                    deck_modal_open = False
                    deck_modal_owner_idx = None
                    deck_modal_cards = []
                    continue
                if discard_modal_open:
                    discard_modal_open = False
                    discard_modal_owner_idx = None
                    discard_modal_cards = []
                    continue
                if game.is_targeting_active():
                    if network_mode:
                        network_status = "Target cancel is disabled in online mode."
                    else:
                        game.cancel_targeting("Target selection cancelled.")
                        _relayout(game)
                    continue
                game.debug("Input: ESC pressed -> exit to menu.")
                return "menu"
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                cx, cy = event.pos
                if log_drawer_handle_rect.collidepoint(cx, cy):
                    log_drawer_open = not log_drawer_open
                    continue
                if log_drawer_open and log_drawer_rect.collidepoint(cx, cy):
                    continue
                if detail_modal_open:
                    modal_rect = _detail_modal_rect()
                    modal_close_rect = _detail_modal_close_rect(modal_rect)
                    if modal_close_rect.collidepoint(cx, cy) or not modal_rect.collidepoint(cx, cy):
                        detail_modal_open = False
                        detail_modal_card = None
                    continue
                if deck_modal_open:
                    modal_rect = _deck_modal_rect()
                    modal_close_rect = _deck_modal_close_rect(modal_rect)
                    if modal_close_rect.collidepoint(cx, cy) or not modal_rect.collidepoint(cx, cy):
                        deck_modal_open = False
                        deck_modal_owner_idx = None
                        deck_modal_cards = []
                    continue
                if discard_modal_open:
                    modal_rect = _discard_modal_rect()
                    modal_close_rect = _discard_modal_close_rect(modal_rect)
                    if modal_close_rect.collidepoint(cx, cy) or not modal_rect.collidepoint(cx, cy):
                        discard_modal_open = False
                        discard_modal_owner_idx = None
                        discard_modal_cards = []
                    continue
                if close_rect.collidepoint(cx, cy):
                    game.debug("Input: close button clicked -> exit to menu.")
                    return "menu"

            if game.phase == Phase.GAME_OVER:
                continue

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                deck_clicked = False
                for idx in range(len(game.players)):
                    _, deck_rect = _pile_rects(idx)
                    if not deck_rect.collidepoint(mx, my):
                        continue
                    deck_clicked = True
                    if _can_open_deck_for_player(
                        idx,
                        game,
                        network_mode=network_mode,
                        my_role=my_role,
                        can_interact=can_interact,
                    ):
                        deck_modal_open = True
                        deck_modal_owner_idx = idx
                        deck_modal_cards = _shuffled_deck_window_cards(game.players[idx])
                    break
                if deck_clicked:
                    continue
                discard_clicked = False
                for idx in range(len(game.players)):
                    discard_rect, _ = _pile_rects(idx)
                    if not discard_rect.collidepoint(mx, my):
                        continue
                    discard_clicked = True
                    discard_modal_open = True
                    discard_modal_owner_idx = idx
                    discard_modal_cards = _ordered_discard_window_cards(game.players[idx])
                    break
                if discard_clicked:
                    continue
                if game.is_targeting_active():
                    if network_mode and not can_interact:
                        continue
                    cancel_rect = _targeting_cancel_rect()
                    if cancel_rect.collidepoint(mx, my):
                        if network_mode:
                            network_status = "Target cancel is disabled in online mode."
                        else:
                            game.cancel_targeting("Target selection cancelled.")
                            _relayout(game)
                        continue
                    clicked_target = None
                    for card in reversed(list(game.targeting_state.get("valid_targets", []))):
                        if card.rect.collidepoint(mx, my):
                            clicked_target = card
                            break
                    if clicked_target is not None:
                        if network_mode:
                            owner_key = _owner_key_for_card(game, clicked_target) or "p1"
                            network_client.send(
                                TARGET_SELECT,
                                {
                                    "card_title": clicked_target.title,
                                    "owner": owner_key,
                                    "card_id": int(getattr(clicked_target, "network_id", 0) or 0),
                                },
                            )
                        elif game.resolve_targeting(clicked_target):
                            _relayout(game)
                    else:
                        game.debug("TARGETING click ignored: no valid target under cursor.")
                    continue
                if end_turn_rect.collidepoint(mx, my) and game.can_end_turn() and can_interact:
                    game.debug(f"Input: End Turn clicked by {active.name}.")
                    if network_mode:
                        network_client.send(END_TURN, {})
                        network_status = "Ending turn..."
                    else:
                        game.end_turn()
                    _relayout(game)
                    continue
                if network_mode and not can_interact:
                    continue
                picked = None
                for card in reversed(controlling_player.hand):
                    if card.rect.collidepoint(mx, my):
                        if game.phase == Phase.MAIN and not game.main_action_taken:
                            picked = card
                        else:
                            game.debug(
                                f"Input ignored: {controlling_player.name} already used the main action."
                            )
                        break
                if picked is None and not network_mode:
                    for card in reversed(controlling_player.on_field):
                        if card.rect.collidepoint(mx, my):
                            picked = card
                            break
                if picked is not None:
                    dragging_card = picked
                    drag_offset = (picked.rect.x - mx, picked.rect.y - my)
                    zone = "hand" if picked in controlling_player.hand else "field"
                    game.debug(f"Input: picked card={picked.title} from {zone}.")

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                mx, my = event.pos
                if detail_modal_open:
                    detail_modal_open = False
                    detail_modal_card = None
                    continue
                if deck_modal_open or discard_modal_open:
                    continue
                if game.is_targeting_active():
                    continue
                inspected: Card | None = None
                for idx, player in enumerate(game.players):
                    if not _is_hand_face_up(idx, game, network_mode=network_mode, my_role=my_role):
                        continue
                    for card in reversed(player.hand):
                        if card.rect.collidepoint(mx, my):
                            inspected = card
                            break
                    if inspected is not None:
                        break
                if inspected is None:
                    for player in game.players:
                        for card in reversed(player.on_field):
                            if card.rect.collidepoint(mx, my):
                                inspected = card
                                break
                        if inspected is not None:
                            break
                if inspected is not None:
                    detail_modal_open = True
                    detail_modal_card = _clone_card(inspected)
                    continue

                if not (pygame.key.get_mods() & pygame.KMOD_CTRL):
                    continue
                if network_mode and not can_interact:
                    continue
                if game.phase != Phase.MAIN or game.main_action_taken:
                    continue
                for card in reversed(controlling_player.hand):
                    if not card.rect.collidepoint(mx, my):
                        continue
                    if network_mode:
                        network_client.send(
                            DISCARD_CARD,
                            {
                                "card_title": card.title,
                                "card_id": int(getattr(card, "network_id", 0) or 0),
                            },
                        )
                        network_status = f"Discarding {card.title}..."
                    elif game.try_discard(card):
                        game.debug(f"Input: CTRL+RMB discard {card.title}.")
                        _relayout(game)
                    break
                else:
                    for card in reversed(controlling_player.on_field):
                        if not card.rect.collidepoint(mx, my):
                            continue
                        trigger = str(getattr(card, "ability_trigger", "") or "").strip().upper()
                        if trigger not in {"ORDER", "ORDER_ZEAL"}:
                            continue
                        if network_mode:
                            network_client.send(
                                ORDER_CARD,
                                {
                                    "card_title": card.title,
                                    "card_id": int(getattr(card, "network_id", 0) or 0),
                                },
                            )
                            network_status = f"Activating ORDER: {card.title}..."
                        elif game.try_order(card):
                            game.debug(f"Input: CTRL+RMB order {card.title}.")
                            _relayout(game)
                        break

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if detail_modal_open:
                    dragging_card = None
                    continue
                if deck_modal_open:
                    dragging_card = None
                    continue
                if game.is_targeting_active():
                    dragging_card = None
                    continue
                if dragging_card is not None and can_interact:
                    opponent = game.opponent
                    if dragging_card in controlling_player.hand:
                        can_play_from_hand = game.phase == Phase.MAIN and not game.main_action_taken
                        if active_field_zone.colliderect(dragging_card.rect) and can_play_from_hand:
                            game.debug(f"Input: drop-to-play {dragging_card.title}.")
                            if network_mode:
                                network_client.send(
                                    PLAY_CARD,
                                    {
                                        "card_title": dragging_card.title,
                                        "card_id": int(getattr(dragging_card, "network_id", 0) or 0),
                                    },
                                )
                                network_status = f"Playing {dragging_card.title}..."
                            else:
                                game.try_play(dragging_card)
                        elif active_field_zone.colliderect(dragging_card.rect):
                            game.debug(
                                f"Input blocked: play denied for {dragging_card.title} because main action is already used."
                            )
                        else:
                            game.debug(f"Input: drop canceled for hand card {dragging_card.title}.")
                    elif not network_mode and dragging_card in controlling_player.on_field:
                        target = None
                        for c in reversed(opponent.on_field):
                            if c.rect.colliderect(dragging_card.rect):
                                target = c
                                break
                        if target is not None:
                            game.debug(f"Input: drop-to-attack {dragging_card.title} -> {target.title}.")
                            game.try_attack(dragging_card, target)
                        else:
                            game.debug(f"Input: drop canceled for field card {dragging_card.title}.")
                    dragging_card = None
                    _relayout(game)

            elif event.type == pygame.MOUSEMOTION and dragging_card is not None:
                if detail_modal_open:
                    continue
                if deck_modal_open:
                    continue
                if game.is_targeting_active():
                    continue
                mx, my = event.pos
                dragging_card.set_topleft(mx + drag_offset[0], my + drag_offset[1])

        if background is not None:
            screen.blit(background, (0, 0))
        else:
            screen.fill(BG_DARK)

        _draw_divider(screen)

        if dragging_card is not None:
            if dragging_card in controlling_player.hand:
                pygame.draw.rect(screen, NEON_GREEN, active_field_zone, width=2)
            elif dragging_card in controlling_player.on_field and not network_mode:
                for c in game.opponent.on_field:
                    if c.rect.colliderect(dragging_card.rect):
                        pygame.draw.rect(screen, NEON_RED, c.rect, width=3)

        for p in game.players:
            for card in p.on_field:
                card.draw(screen)
        for idx, p in enumerate(game.players):
            face_up = _is_hand_face_up(idx, game, network_mode=network_mode, my_role=my_role)
            hovered_hand_card = hovered_hand_cards.get(idx)
            for card in p.hand:
                if card is dragging_card:
                    continue
                if face_up and card is hovered_hand_card:
                    continue
                if face_up:
                    card.draw(screen)
                else:
                    _draw_card_back(screen, card.rect, fonts)
            if face_up and hovered_hand_card is not None and hovered_hand_card is not dragging_card:
                hovered_hand_card.draw(screen)
        pile_hovered_card, pile_hovered_anchor = _draw_side_piles(
            screen,
            game,
            fonts,
            network_mode=network_mode,
            my_role=my_role,
            can_interact=can_interact,
            mx=mx,
            my=my,
        )
        modal_hovered_card: Card | None = None
        modal_hovered_anchor: pygame.FRect | None = None
        discard_modal_hovered_card: Card | None = None
        discard_modal_hovered_anchor: pygame.FRect | None = None
        hovered_hand_hint_card: Card | None = None
        for card in hovered_hand_cards.values():
            if card.rect.collidepoint(mx, my):
                hovered_hand_hint_card = card
                break
        hovered_field_hint_card: Card | None = None
        if (
            hovered_hand_hint_card is None
            and dragging_card is None
            and not game.is_targeting_active()
            and not deck_modal_open
            and not discard_modal_open
            and not detail_modal_open
        ):
            for p in game.players:
                for c in reversed(p.on_field):
                    if c.rect.collidepoint(mx, my):
                        hovered_field_hint_card = c
                        break
                if hovered_field_hint_card is not None:
                    break
        hovered_brief_card = hovered_hand_hint_card or hovered_field_hint_card
        if dragging_card is not None:
            dragging_card.draw(screen)
        particle_system.update()
        particle_system.draw(screen)

        if game.is_targeting_active():
            _draw_targeting_overlay(screen, game, fonts)

        log_drawer_rect, log_drawer_handle_rect = _draw_action_log_drawer(
            screen,
            game,
            fonts,
            is_open=log_drawer_open,
            mx=mx,
            my=my,
        )
        _draw_hud(screen, game, fonts)
        end_turn_enabled = game.can_end_turn() and can_interact
        _draw_end_turn_button(screen, end_turn_rect, end_turn_enabled, fonts)
        if network_mode:
            _draw_network_status(screen, fonts, my_role, bool(is_my_turn and game.phase != Phase.GAME_OVER), network_status)
        draw_close_button(screen, fonts, hovered=close_rect.collidepoint(mx, my))
        if deck_modal_open and deck_modal_owner_idx in {0, 1}:
            _, _, modal_hovered_card, modal_hovered_anchor = _draw_deck_modal(
                screen,
                fonts,
                game.players[deck_modal_owner_idx],
                deck_modal_cards,
                mx=mx,
                my=my,
            )
        if discard_modal_open and discard_modal_owner_idx in {0, 1}:
            _, _, discard_modal_hovered_card, discard_modal_hovered_anchor = _draw_discard_modal(
                screen,
                fonts,
                game.players[discard_modal_owner_idx],
                discard_modal_cards,
                mx=mx,
                my=my,
            )
        if detail_modal_open and detail_modal_card is not None:
            _draw_detail_modal(screen, fonts, detail_modal_card, mx=mx, my=my)
        elif (
            hovered_brief_card is not None
            and dragging_card is None
            and not game.is_targeting_active()
            and not deck_modal_open
            and not discard_modal_open
        ):
            _draw_hand_ability_hint(screen, fonts, hovered_brief_card)

        if (
            dragging_card is None
            and game.phase != Phase.GAME_OVER
            and not game.is_targeting_active()
            and not detail_modal_open
        ):
            hovered: Card | None = None
            hovered_anchor: pygame.FRect | None = None
            if deck_modal_open and modal_hovered_card is not None:
                hovered = modal_hovered_card
                hovered_anchor = modal_hovered_anchor
            elif discard_modal_open and discard_modal_hovered_card is not None:
                hovered = discard_modal_hovered_card
                hovered_anchor = discard_modal_hovered_anchor
            else:
                if hovered_brief_card is None:
                    for c in reversed(controlling_player.hand):
                        if c.rect.collidepoint(mx, my):
                            hovered = c
                            hovered_anchor = c.rect
                            break
                if hovered is None and hovered_brief_card is None:
                    for p in game.players:
                        for c in reversed(p.on_field):
                            if c.rect.collidepoint(mx, my):
                                hovered = c
                                hovered_anchor = c.rect
                                break
                        if hovered is not None:
                            break
                if hovered is None and pile_hovered_card is not None:
                    hovered = pile_hovered_card
                    hovered_anchor = pile_hovered_anchor
            if hovered is not None:
                draw_hover_panel(screen, hovered, fonts, hovered_anchor or hovered.rect)

        if game.phase == Phase.GAME_OVER:
            _draw_game_over(screen, game, fonts)

        pygame.display.flip()
