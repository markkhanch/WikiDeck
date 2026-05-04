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
import time
import pygame

from config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    WINDOW_TITLE,
    BG_IMAGE_PATH,
)
from core.card import Card
from core.card_factory import build_card, build_card_from_spec
from data.db import init_db
from data.db import deck_size, get_deck_cards, get_cached_card
from data.booster import ensure_shop_singles
from data.ollama_gen import (
    apply_diversity,
    generate_card_spec,
    ollama_available,
    get_article_from_pool,
)
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

STARTER_CARDS = [
    ("Albert Einstein",        "LIVING",     3, 4, "DRAW_1",         "NONE"),
    ("Charles Darwin",         "LIVING",     4, 3, "NONE",           "DRAW_1"),
    ("William Shakespeare",    "LIVING",     3, 3, "NONE",           "NONE"),
    ("Moon",                   "PLACES",     4, 3, "NONE",           "NONE"),
    ("Mount Everest",          "PLACES",     6, 2, "NONE",           "NONE"),
    ("Pacific Ocean",          "PLACES",     7, 1, "HEAL_SELF_2",    "NONE"),
    ("World War II",           "EVENTS",     3, 5, "DAMAGE_ENEMY_2", "NONE"),
    ("French Revolution",      "EVENTS",     4, 4, "NONE",           "DAMAGE_ENEMY_2"),
    ("Renaissance",            "EVENTS",     4, 3, "BUFF_SELF_1",    "NONE"),
    ("Fire",                   "SCIENCE",    4, 3, "DAMAGE_ENEMY_2", "NONE"),
    ("Water",                  "SCIENCE",    5, 2, "NONE",           "NONE"),
    ("Sun",                    "SCIENCE",    3, 4, "NONE",           "NONE"),
    ("Computer",               "TECHNOLOGY", 3, 4, "DRAW_1",         "NONE"),
    ("Internet",               "TECHNOLOGY", 2, 5, "DRAW_1",         "NONE"),
    ("Wheel",                  "TECHNOLOGY", 4, 2, "NONE",           "NONE"),
    ("Jazz",                   "CULTURE",    3, 3, "NONE",           "NONE"),
    ("Great Pyramid of Giza",  "CULTURE",    6, 2, "NONE",           "NONE"),
    ("Democracy",              "CONCEPTS",   5, 2, "NONE",           "NONE"),
    ("Gravity",                "CONCEPTS",   4, 3, "BUFF_SELF_1",    "NONE"),
    ("Time",                   "CONCEPTS",   3, 3, "NONE",           "DRAW_1"),
]

def load_background() -> pygame.Surface | None:
    if not os.path.isfile(BG_IMAGE_PATH):
        return None
    bg = pygame.image.load(BG_IMAGE_PATH).convert()
    return pygame.transform.scale(bg, (SCREEN_WIDTH, SCREEN_HEIGHT))


def build_starter_base_cards() -> list[Card]:
    """Fetch each Wikipedia article once; return a list of Card templates."""
    from core.effects import Effect
    print("Building starter deck — fetching Wikipedia articles...")
    cards = []
    for title, theme, hp, base_score, on_play_str, on_death_str in STARTER_CARDS:
        print(f"  {title} ...")
        on_play = getattr(Effect, on_play_str, Effect.NONE)
        on_death = getattr(Effect, on_death_str, Effect.NONE)
        cards.append(build_card(title, theme, hp, base_score, on_play, on_death, rarity="COMMON"))
    return cards


def build_ai_base_cards(target_count: int) -> list[Card]:
    """Generate cards via Ollama; fall back to starter cards if needed."""
    print("Building AI deck — generating cards with Ollama...")
    cards: list[Card] = []
    seen: set[str] = set()
    attempts = 0
    max_attempts = target_count * 12
    diversity = {"effects": {}, "triggers": {}, "target": target_count}

    while len(cards) < target_count:
        attempts += 1
        if attempts > max_attempts:
            raise RuntimeError(
                "Unable to fetch enough Wikipedia images. "
                "Check network access to Wikipedia and try again."
            )
        title, summary, rarity = get_article_from_pool()
        if title in seen:
            continue
        spec = generate_card_spec(title, summary, rarity, diversity=diversity)

        card = build_card_from_spec(spec)
        if card.image is None:
            print(f"  [skip] No image for {spec['title']}, retrying...", flush=True)
            continue
        cards.append(card)
        apply_diversity(diversity, spec)
        seen.add(title)
        print(f"  [{len(cards)}/{target_count}] {spec['title']} ✓", flush=True)
        time.sleep(0.25)

    return cards


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

    ensure_shop_singles(min_count=2)
    background = load_background()

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
            state = run_match(screen, fonts, background, base_cards)
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
            state = run_match(
                screen,
                fonts,
                background,
                [],
                network_client=network_session.get("client"),
                network_role=network_session.get("role"),
            )
            _cleanup_network_session(network_session)
            network_session = None
        else:
            state = "menu"

    _cleanup_network_session(network_session)
    pygame.quit()


if __name__ == "__main__":
    run_app()
