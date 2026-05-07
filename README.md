# WikiDeck

A PvP collectible card game where every card is a real Wikipedia article.

Built with Python, Pygame, and Ollama for CS 108 — Spring 2026.

## What is this?

WikiDeck turns Wikipedia's knowledge graph into a card game. Every card 
is generated from a real Wikipedia article — its stats, abilities, and 
rarity come from real data like pageviews and article quality. Players 
build decks, compete in local network matches, and win by combining cards 
that are actually connected on Wikipedia.

## Status

Active development. Everything is subject to change.

## Setup

1. Install dependencies:
   `pip3 install -r requirements.txt`
2. (Optional) Set custom Ollama endpoint:
   `export WIKIDECK_OLLAMA_HOST=http://127.0.0.1:11434`

## Settings

- Open **Settings** from the main menu to configure gameplay, AI/Ollama, shop economy, networking, and debug flags.
- Settings are persisted in SQLite (`data/wikideck.db`, table `app_settings`).
- Environment variables in `config.py` are used as initial defaults; after first launch, in-game settings become the source of truth.

## Tech Stack

- Python + Pygame — game engine and UI
- Ollama — local LLM for card ability generation
- Wikipedia REST API — card data and knowledge graph
- SQLite — local card database and player profiles

## Tools Used

This project uses **Pygame** for the game client and **Ollama** 
(connected to the WWU CS course server) for AI-powered card generation.

## AI Use

Ollama is used to generate card abilities from Wikipedia article summaries.

## Security Notes (before publishing)

- Do not commit local runtime data: `data/wikideck.db`, `ui/assets/card_images/`, `.env*`.
- Do not commit local tooling settings: `.vscode/`, `__pycache__/`, `.DS_Store`.
- Multiplayer server is WebSocket MVP with no authentication/encryption layer; run only on trusted LAN unless you add auth/TLS.

## Author

Mark Khanchevskii — CS 108, Walla Walla University
