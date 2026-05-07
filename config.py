"""Global constants for WikiDeck.

Referenced sections are from docs/WikiDeck.docx (GDD v0.2).
"""
import os

# ---- Paths ----
_ROOT = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(_ROOT, "ui", "assets")
IMAGES_DIR = os.path.join(ASSETS_DIR, "images")

BG_IMAGE_PATH   = os.path.join(IMAGES_DIR, "bg_main.png")
CARD_IMAGES_DIR = os.path.join(ASSETS_DIR, "card_images")
DB_PATH         = os.path.join(_ROOT, "data", "wikideck.db")

# ---- Ollama (AI card generation) ----
USE_OLLAMA_GENERATOR = os.getenv("WIKIDECK_USE_OLLAMA", "1") == "1"
_OLLAMA_HOST_LOCAL_FILE = os.path.join(_ROOT, ".ollama_host")
_OLLAMA_HOST_LOCAL = ""
if os.path.isfile(_OLLAMA_HOST_LOCAL_FILE):
    try:
        with open(_OLLAMA_HOST_LOCAL_FILE, "r", encoding="utf-8") as _f:
            _OLLAMA_HOST_LOCAL = _f.read().strip()
    except OSError:
        _OLLAMA_HOST_LOCAL = ""
OLLAMA_HOST = os.getenv("WIKIDECK_OLLAMA_HOST", _OLLAMA_HOST_LOCAL or "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv(
    "WIKIDECK_OLLAMA_MODEL",
    "qwen2.5-coder:14b",
)
OLLAMA_MAX_RETRIES = int(os.getenv("WIKIDECK_OLLAMA_MAX_RETRIES", "3"))

# ---- Window ----
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60
WINDOW_TITLE = "WikiDeck"

# ---- Global palette (GDD §11.2) ----
BG_DARK    = (0x0D, 0x0D, 0x1A)
BG_MID     = (0x1A, 0x1A, 0x2E)
BG_LIGHT   = (0x2A, 0x2A, 0x4A)
NEON_GREEN = (0x00, 0xFF, 0x9C)
NEON_BLUE  = (0x00, 0xBF, 0xFF)
NEON_RED   = (0xFF, 0x44, 0x44)
GOLD       = (0xFF, 0xD7, 0x00)
WHITE_TEXT = (0xE8, 0xE8, 0xE8)
MUTED_TEXT = (0x88, 0x88, 0x88)

# ---- Theme colors (GDD §11.3) ----
THEME_COLORS = {
    "LIVING":     (0x2E, 0x7D, 0x32),
    "PLACES":     (0x15, 0x65, 0xC0),
    "EVENTS":     (0xB7, 0x1C, 0x1C),
    "SCIENCE":    (0x6A, 0x1B, 0x9A),
    "TECHNOLOGY": (0xE6, 0x51, 0x00),
    "CULTURE":    (0x88, 0x0E, 0x4F),
    "CONCEPTS":   (0xF5, 0x7F, 0x17),
}

# ---- Rarity border colors (GDD §11.4) ----
RARITY_COLORS = {
    "COMMON":    (0x88, 0x88, 0x88),
    "UNCOMMON":  (0x43, 0xA0, 0x47),
    "RARE":      (0x1E, 0x88, 0xE5),
    "EPIC":      (0x8E, 0x24, 0xAA),
    "LEGENDARY": (0xFF, 0xD7, 0x00),
}

# ---- Card sizes (GDD §11.5) ----
CARD_WIDTH = 100    # compact state, in hand
CARD_HEIGHT = 140

# ---- Layout — two-player hotseat (GDD §11.8, simplified) ----
# P1 bottom, P2 top. Active player is just a game-state flag; visuals stay put.
P1_HAND_CENTER_Y  = 625
P1_FIELD_CENTER_Y = 425
P2_FIELD_CENTER_Y = 255
P2_HAND_CENTER_Y  = 95

HAND_SPACING  = 12
FIELD_SPACING = 12

# Drop zones — rectangle the card must land on to be played.
# Each covers exactly the field row of the corresponding player.
P1_FIELD_ZONE = (0, 355, SCREEN_WIDTH, 140)
P2_FIELD_ZONE = (0, 185, SCREEN_WIDTH, 140)

# Visual divider between the two halves of the board
DIVIDER_Y = 340

# End Turn button — middle-right
END_TURN_BUTTON_RECT = (SCREEN_WIDTH - 195, SCREEN_HEIGHT // 2 - 25, 180, 50)

# ---- Match parameters (GDD §5.1 — trimmed for MVP) ----
STARTING_HAND_SIZE = 5    # full game says 10; use 5 while deck is small
FIELD_LIMIT        = 15

# ---- Deck / Booster ----
DECK_MIN = 15
DECK_MAX = 25
DECK_TARGET = 20
