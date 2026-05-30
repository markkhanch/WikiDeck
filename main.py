"""WikiDeck entry point.

Stage 3 MVP — hotseat match:
 - Two players on the same keyboard, P1 bottom / P2 top
 - Turn order: DRAW (auto-draw 1) → MAIN (play OR discard one card) → End Turn
 - Only the active player can drag cards
 - LMB drag from hand → field zone plays the card
 - RMB on hand card → discards it
 - End Turn button bottom-right, enabled once MAIN is done (or hand is empty)
 - Match ends when both players are out of cards → scoreboard overlay
"""
import os
import pygame

from config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    WINDOW_TITLE,
    BG_IMAGE_PATH,
)
from core.card import Card
from core.card_factory import build_card_from_spec
from core.sound_player import start_menu_music, stop_menu_music
from data.db import init_db
from data.db import deck_size, get_deck_cards, get_cached_card
from data.booster import ensure_shop_singles
from data.settings_service import ensure_loaded, get_bool, get_int
from ui.screens.collection import run_collection
from ui.screens.deck_builder import run_deck_builder
from ui.screens.main_menu import run_main_menu
from ui.screens.match import run_match
from ui.screens.network_connect import run_host_game, run_join_game
from ui.screens.play import run_play_menu
from ui.screens.profile import run_profile
from ui.screens.settings import run_settings
from ui.screens.shop import run_shop


# ---------- asset loading ----------

def load_background() -> pygame.Surface | None:
    if not os.path.isfile(BG_IMAGE_PATH):
        return None
    bg = pygame.image.load(BG_IMAGE_PATH).convert()
    return pygame.transform.scale(bg, (SCREEN_WIDTH, SCREEN_HEIGHT))


def build_cards_from_deck() -> list[Card]:
    base_cards: list[Card] = []
    for entry in get_deck_cards():
        spec = get_cached_card(entry["title"], entry["rarity"])
        if spec is None:
            continue
        for _ in range(entry["count"]):
            base_cards.append(build_card_from_spec(spec))
    return base_cards



def make_fonts() -> dict:
    return {
        "hud":         pygame.font.SysFont("arial", 18, bold=True),
        "big":         pygame.font.SysFont("arial", 48, bold=True),
        "med":         pygame.font.SysFont("arial", 24, bold=True),
        "small":       pygame.font.SysFont("arial", 14, bold=False),
        "panel_title": pygame.font.SysFont("arial", 20, bold=True),
    }


def _cleanup_network_session(session: dict | None) -> None:
    if not session:
        return
    client = session.get("client")
    server_handle = session.get("server_handle")
    if client is not None:
        client.close()
    if server_handle is not None:
        server_handle.stop()


# ---------- main ----------

def run_app() -> None:
    pygame.init()
    init_db()
    ensure_loaded()
    display_flags = pygame.FULLSCREEN if get_bool("display.fullscreen") else 0
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), display_flags)
    pygame.display.set_caption(WINDOW_TITLE)
    fonts = make_fonts()

    ensure_shop_singles(min_count=2, background=True)
    background = load_background()

    # Background menu music — plays everywhere except during matches.
    start_menu_music()

    state: str | None = "menu"
    network_session: dict | None = None
    while state is not None:
        if state == "menu":
            state = run_main_menu(screen, fonts, background)
        elif state == "play":
            state = run_play_menu(
                screen,
                fonts,
                background,
                deck_size(),
                get_int("gameplay.deck_min"),
            )
        elif state == "match":
            base_cards = build_cards_from_deck()
            stop_menu_music()
            state = run_match(screen, fonts, background, base_cards)
            start_menu_music()
        elif state == "collection":
            state = run_collection(screen, fonts, background)
        elif state == "deck_builder":
            state = run_deck_builder(screen, fonts, background)
        elif state == "shop":
            state = run_shop(screen, fonts, background)
        elif state == "profile":
            state = run_profile(screen, fonts, background)
        elif state == "settings":
            state = run_settings(screen, fonts, background)
            current_screen = pygame.display.get_surface()
            if current_screen is not None:
                screen = current_screen
        elif state == "host_game":
            result = run_host_game(screen, fonts, background)
            if isinstance(result, dict):
                network_session = result
                state = "network_match"
            else:
                state = result
        elif state == "join_game":
            result = run_join_game(screen, fonts, background)
            if isinstance(result, dict):
                network_session = result
                state = "network_match"
            else:
                state = result
        elif state == "network_match":
            if not network_session:
                state = "menu"
                continue
            stop_menu_music()
            state = run_match(
                screen,
                fonts,
                background,
                [],
                network_client=network_session.get("client"),
                network_role=network_session.get("role"),
            )
            start_menu_music()
            _cleanup_network_session(network_session)
            network_session = None
        else:
            state = "menu"

    _cleanup_network_session(network_session)
    pygame.quit()


if __name__ == "__main__":
    run_app()
