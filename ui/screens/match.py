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
    HAND_SPACING,
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
        base_score=c.base_score,
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


def _layout_row(cards: list[Card], center_y: int, spacing: int) -> None:
    n = len(cards)
    if n == 0:
        return
    total_w = n * CARD_WIDTH + (n - 1) * spacing
    start_x = (SCREEN_WIDTH - total_w) // 2
    for i, card in enumerate(cards):
        x = start_x + i * (CARD_WIDTH + spacing)
        card.set_topleft(x, center_y - CARD_HEIGHT // 2)


def _relayout(game: GameState) -> None:
    p1, p2 = game.players
    _layout_row(p1.hand,     P1_HAND_CENTER_Y,  HAND_SPACING)
    _layout_row(p1.on_field, P1_FIELD_CENTER_Y, FIELD_SPACING)
    _layout_row(p2.hand,     P2_HAND_CENTER_Y,  HAND_SPACING)
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


def _draw_hud(screen: pygame.Surface, game: GameState, fonts: dict) -> None:
    p1, p2 = game.players
    active = game.active_player

    center_text = f"Turn {game.turn_number}  —  {active.name}'s turn ({game.phase.value})"
    surf = fonts["hud"].render(center_text, True, NEON_GREEN)
    screen.blit(surf, surf.get_rect(midtop=(SCREEN_WIDTH // 2, 4)))

    if game.last_event:
        ev = fonts["small"].render(game.last_event, True, GOLD)
        screen.blit(ev, ev.get_rect(midtop=(SCREEN_WIDTH // 2, 26)))

    def player_label(p: Player) -> str:
        base = game.base_sum(p)
        mult = game.multiplier_for(p)
        score = game.score_for(p)
        combos = game.active_combos_for(p)
        combo_str = "  ".join(f"{n} +{b:.1f}x" for n, b in combos)
        line = (
            f"{p.name}  H:{len(p.hand)}  D:{len(p.deck)}  F:{len(p.on_field)}  "
            f"Score {score} ({base} × {mult:.1f})"
        )
        if combo_str:
            line += f"    [{combo_str}]"
        return line

    p1_color = NEON_GREEN if active is p1 else MUTED_TEXT
    p2_color = NEON_GREEN if active is p2 else MUTED_TEXT
    screen.blit(fonts["small"].render(player_label(p1), True, p1_color),
                (10, SCREEN_HEIGHT - 20))
    screen.blit(fonts["small"].render(player_label(p2), True, p2_color),
                (10, 4))

    if game.action_log:
        base_y = SCREEN_HEIGHT - 140
        panel = pygame.Rect(8, base_y - 8, 520, 120)
        pygame.draw.rect(screen, BG_DARK, panel)
        pygame.draw.rect(screen, NEON_BLUE, panel, width=1)
        title = fonts["small"].render("Action Log", True, GOLD)
        screen.blit(title, (panel.x + 8, panel.y + 6))
        for idx, line in enumerate(game.action_log[-5:]):
            text = fonts["small"].render(f"- {line}", True, WHITE_TEXT)
            screen.blit(text, (panel.x + 8, panel.y + 28 + idx * 18))


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
        "BOOST",
        "SHIELD",
        "POISON",
        "DESTROY",
        "BANISH",
        "DEPLOY",
        "DEATHWISH",
        "GOLD",
        "DRAW",
        "DRAIN",
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
    screen.blit(left, (10, SCREEN_HEIGHT - 44))
    if status_line:
        right = fonts["small"].render(status_line, True, GOLD)
        screen.blit(right, (10, SCREEN_HEIGHT - 62))


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

        active = game.active_player
        my_player = _player_for_role(game, my_role) if network_mode else active
        controlling_player = my_player if my_player is not None else active
        is_my_turn = (not network_mode) or bool(getattr(network_client, "is_my_turn", False))
        can_interact = (not network_mode) or (my_player is not None and is_my_turn)
        if my_role == "p1":
            my_field_zone = p1_field_zone
        elif my_role == "p2":
            my_field_zone = p2_field_zone
        else:
            my_field_zone = p1_field_zone if game.active_idx == 0 else p2_field_zone
        active_field_zone = my_field_zone if network_mode else (p1_field_zone if game.active_idx == 0 else p2_field_zone)
        mx, my = pygame.mouse.get_pos()
        close_rect = close_button_rect()
        _layout_discard_targets(game)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if game.is_targeting_active():
                    if network_mode:
                        network_status = "Target cancel is disabled in online mode."
                    else:
                        game.cancel_targeting("Target selection cancelled.")
                        _relayout(game)
                    continue
                game.debug("Input: ESC pressed -> exit to menu.")
                return "menu"
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and close_rect.collidepoint(mx, my):
                game.debug("Input: close button clicked -> exit to menu.")
                return "menu"

            if game.phase == Phase.GAME_OVER:
                continue

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
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
                        picked = card
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
                if network_mode and not can_interact:
                    continue
                if game.is_targeting_active():
                    continue
                mx, my = event.pos
                for card in reversed(controlling_player.hand):
                    if card.rect.collidepoint(mx, my):
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
                            game.debug(f"Input: RMB discard {card.title}.")
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
                            game.debug(f"Input: RMB order {card.title}.")
                            _relayout(game)
                        break

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if game.is_targeting_active():
                    dragging_card = None
                    continue
                if dragging_card is not None and can_interact:
                    opponent = game.opponent
                    if dragging_card in controlling_player.hand:
                        if active_field_zone.colliderect(dragging_card.rect):
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
            if network_mode:
                face_up = (my_role == "p1" and idx == 0) or (my_role == "p2" and idx == 1)
            else:
                face_up = (idx == game.active_idx)
            for card in p.hand:
                if card is dragging_card:
                    continue
                if face_up:
                    card.draw(screen)
                else:
                    _draw_card_back(screen, card.rect, fonts)
        if dragging_card is not None:
            dragging_card.draw(screen)
        particle_system.update()
        particle_system.draw(screen)

        if game.is_targeting_active():
            _draw_targeting_overlay(screen, game, fonts)

        _draw_hud(screen, game, fonts)
        end_turn_enabled = game.can_end_turn() and can_interact
        _draw_end_turn_button(screen, end_turn_rect, end_turn_enabled, fonts)
        if network_mode:
            _draw_network_status(screen, fonts, my_role, bool(is_my_turn and game.phase != Phase.GAME_OVER), network_status)
        draw_close_button(screen, fonts, hovered=close_rect.collidepoint(mx, my))

        if dragging_card is None and game.phase != Phase.GAME_OVER and not game.is_targeting_active():
            hovered: Card | None = None
            for c in reversed(controlling_player.hand):
                if c.rect.collidepoint(mx, my):
                    hovered = c
                    break
            if hovered is None:
                for p in game.players:
                    for c in reversed(p.on_field):
                        if c.rect.collidepoint(mx, my):
                            hovered = c
                            break
                    if hovered is not None:
                        break
            if hovered is not None:
                draw_hover_panel(screen, hovered, fonts, hovered.rect)

        if game.phase == Phase.GAME_OVER:
            _draw_game_over(screen, game, fonts)

        pygame.display.flip()
