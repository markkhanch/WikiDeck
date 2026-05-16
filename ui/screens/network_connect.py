import socket
import ipaddress

import pygame

from config import SCREEN_WIDTH
from core.sound_player import play_click
from data.settings_service import network_ports, target_fps
from network.client import NetworkClient
from network.protocol import CONNECTION_STATUS, ERROR, GAME_STATE, ROLE
from network.server import ServerHandle, start_background_server
from ui.screens.common import (
    close_button_rect,
    draw_back_hint,
    draw_background,
    draw_button,
    draw_close_button,
    draw_title,
)


def _is_valid_host_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if not isinstance(addr, ipaddress.IPv4Address):
        return False
    return not (addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_unspecified)


def _local_ip() -> str:
    candidates: list[str] = []

    for target in (("8.8.8.8", 80), ("1.1.1.1", 80), ("192.168.0.1", 80), ("10.0.0.1", 80)):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(target)
                ip = str(sock.getsockname()[0] or "").strip()
                if _is_valid_host_ip(ip):
                    candidates.append(ip)
        except OSError:
            continue

    try:
        _name, _aliases, ips = socket.gethostbyname_ex(socket.gethostname())
        for ip in ips:
            ip = str(ip or "").strip()
            if _is_valid_host_ip(ip):
                candidates.append(ip)
    except OSError:
        pass

    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_DGRAM)
        for info in infos:
            ip = str(info[4][0] or "").strip()
            if _is_valid_host_ip(ip):
                candidates.append(ip)
    except OSError:
        pass

    unique = list(dict.fromkeys(candidates))
    if not unique:
        return "127.0.0.1"

    for ip in unique:
        try:
            if ipaddress.ip_address(ip).is_private:
                return ip
        except ValueError:
            continue
    return unique[0]


def _parse_host_value(raw: str) -> tuple[str, tuple[int, ...]]:
    default_ports = network_ports()
    value = (raw or "").strip()
    if not value:
        return "127.0.0.1", default_ports
    if ":" in value:
        host, _, port_raw = value.partition(":")
        try:
            port = int(port_raw.strip())
            return host.strip() or "127.0.0.1", (port,)
        except ValueError:
            return host.strip() or "127.0.0.1", default_ports
    return value, default_ports


def _cleanup(client: NetworkClient | None, server_handle: ServerHandle | None) -> None:
    if client is not None:
        client.close()
    if server_handle is not None:
        server_handle.stop()


def run_host_game(screen: pygame.Surface, fonts: dict, background: pygame.Surface | None) -> dict | str | None:
    clock = pygame.time.Clock()
    local_ip = _local_ip()
    server_handle: ServerHandle | None = None
    client: NetworkClient | None = None
    role: str | None = None
    status = "Starting server..."
    try:
        server_handle = start_background_server()
        client = NetworkClient()
        client.connect("127.0.0.1", ports=(server_handle.port,))
        status = f"Server started on port {server_handle.port}. Connecting as host..."
    except Exception as exc:
        status = f"Failed to start host server: {exc}"

    while True:
        clock.tick(target_fps())
        mx, my = pygame.mouse.get_pos()
        close_rect = close_button_rect()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _cleanup(client, server_handle)
                return None
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                play_click()
                _cleanup(client, server_handle)
                return "menu"
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and close_rect.collidepoint(mx, my):
                play_click()
                _cleanup(client, server_handle)
                return "menu"

        if client is not None:
            messages = client.poll()
            for idx, msg in enumerate(messages):
                msg_type = msg.get("type")
                data = msg.get("data", {})
                if msg_type == ROLE:
                    role = str(data.get("role", "") or "")
                    status = f"Connected as {role}. Waiting for opponent..."
                elif msg_type == CONNECTION_STATUS:
                    connection_status = str(data.get("status", ""))
                    if connection_status == "connected":
                        status = "Connected. Waiting for opponent..."
                    elif connection_status == "failed":
                        status = str(data.get("error", "Connection failed"))
                    elif connection_status == "closed":
                        status = "Connection closed."
                elif msg_type == GAME_STATE:
                    client.requeue_messages(messages[idx:])
                    return {"client": client, "server_handle": server_handle, "role": role}
                elif msg_type == ERROR:
                    status = str(data.get("text", "Unknown network error"))

        draw_background(screen, background)
        draw_title(screen, "HOST GAME", fonts, y=90)

        ip_text = fonts["med"].render(f"Your IP: {local_ip}", True, (255, 255, 255))
        screen.blit(ip_text, ip_text.get_rect(center=(SCREEN_WIDTH // 2, 220)))
        if server_handle is not None:
            port_text = fonts["small"].render(f"Port: {server_handle.port}", True, (170, 170, 170))
            screen.blit(port_text, port_text.get_rect(center=(SCREEN_WIDTH // 2, 255)))

        waiting = "Waiting for opponent..." if client is not None else "Host startup failed."
        waiting_text = fonts["med"].render(waiting, True, (0, 255, 156))
        screen.blit(waiting_text, waiting_text.get_rect(center=(SCREEN_WIDTH // 2, 330)))

        status_text = fonts["small"].render(status, True, (255, 215, 0))
        screen.blit(status_text, status_text.get_rect(center=(SCREEN_WIDTH // 2, 380)))

        host_hint = fonts["small"].render("Join from another PC using this IP.", True, (170, 170, 170))
        screen.blit(host_hint, host_hint.get_rect(center=(SCREEN_WIDTH // 2, 430)))

        draw_close_button(screen, fonts, hovered=close_rect.collidepoint(mx, my))
        draw_back_hint(screen, fonts)
        pygame.display.flip()


def run_join_game(screen: pygame.Surface, fonts: dict, background: pygame.Surface | None) -> dict | str | None:
    clock = pygame.time.Clock()
    input_rect = pygame.Rect((SCREEN_WIDTH - 420) // 2, 240, 420, 48)
    connect_rect = pygame.Rect((SCREEN_WIDTH - 220) // 2, 315, 220, 52)
    host_text = "127.0.0.1"
    typing_active = True
    status = "Enter host IP (example: 192.168.1.45)"
    client: NetworkClient | None = None
    role: str | None = None
    connected = False

    while True:
        clock.tick(target_fps())
        mx, my = pygame.mouse.get_pos()
        close_rect = close_button_rect()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _cleanup(client, None)
                return None
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                play_click()
                _cleanup(client, None)
                return "menu"
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if close_rect.collidepoint(mx, my):
                    play_click()
                    _cleanup(client, None)
                    return "menu"
                typing_active = input_rect.collidepoint(mx, my)
                if connect_rect.collidepoint(mx, my):
                    play_click()
                    if client is not None:
                        client.close()
                    host, ports = _parse_host_value(host_text)
                    client = NetworkClient()
                    client.connect(host, ports=ports)
                    connected = False
                    status = "Connecting..."
            if event.type == pygame.KEYDOWN and typing_active:
                if event.key == pygame.K_BACKSPACE:
                    host_text = host_text[:-1]
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    host, ports = _parse_host_value(host_text)
                    if client is not None:
                        client.close()
                    client = NetworkClient()
                    client.connect(host, ports=ports)
                    connected = False
                    status = "Connecting..."
                elif event.unicode and event.unicode.isprintable():
                    if len(host_text) < 64:
                        host_text += event.unicode

        if client is not None:
            messages = client.poll()
            for idx, msg in enumerate(messages):
                msg_type = msg.get("type")
                data = msg.get("data", {})
                if msg_type == CONNECTION_STATUS:
                    connection_status = str(data.get("status", ""))
                    if connection_status == "connected":
                        connected = True
                        status = "Connected! Waiting for game state..."
                    elif connection_status == "failed":
                        connected = False
                        status = str(data.get("error", "Connection failed"))
                    elif connection_status == "closed" and not connected:
                        status = "Connection closed."
                elif msg_type == ROLE:
                    role = str(data.get("role", "") or "")
                    status = f"Connected as {role}. Waiting for host..."
                elif msg_type == GAME_STATE:
                    client.requeue_messages(messages[idx:])
                    return {"client": client, "server_handle": None, "role": role}
                elif msg_type == ERROR:
                    status = str(data.get("text", "Network error"))

        draw_background(screen, background)
        draw_title(screen, "JOIN GAME", fonts, y=90)

        hint = fonts["small"].render("Enter host IP (or IP:port)", True, (170, 170, 170))
        screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, 210)))

        border = (0, 255, 156) if typing_active else (140, 140, 140)
        pygame.draw.rect(screen, (26, 26, 46), input_rect)
        pygame.draw.rect(screen, border, input_rect, width=2)
        ip_surf = fonts["med"].render(host_text or "", True, (232, 232, 232))
        screen.blit(ip_surf, (input_rect.x + 12, input_rect.y + 10))

        draw_button(screen, connect_rect, "CONNECT", fonts, hovered=connect_rect.collidepoint(mx, my), enabled=True)

        status_surf = fonts["small"].render(status, True, (255, 215, 0))
        screen.blit(status_surf, status_surf.get_rect(center=(SCREEN_WIDTH // 2, 405)))

        draw_close_button(screen, fonts, hovered=close_rect.collidepoint(mx, my))
        draw_back_hint(screen, fonts)
        pygame.display.flip()
