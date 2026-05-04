"""WebSocket network client for multiplayer WikiDeck sessions."""

from __future__ import annotations

import asyncio
import queue
import threading
import time
from typing import Iterable

import websockets

from data.settings_service import get_bool, network_ports
from network.protocol import (
    CONNECTION_STATUS,
    ERROR,
    ROLE,
    YOUR_TURN,
    decode,
    encode,
    make_message,
)


class NetworkClient:
    def __init__(self) -> None:
        self.role: str | None = None
        self.is_my_turn = False
        self.incoming: queue.Queue[dict] = queue.Queue()
        self.outgoing: queue.Queue[dict] = queue.Queue()
        self.ws = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread: threading.Thread | None = None
        self.connected_host: str | None = None
        self.connected_port: int | None = None
        self._stop_event = threading.Event()

    def _log(self, text: str) -> None:
        if not get_bool("debug.network_verbose_logs"):
            return
        ts = time.strftime("%H:%M:%S")
        print(f"[net-client][{ts}] {text}", flush=True)

    def connect(self, host: str, ports: Iterable[int] | None = None) -> None:
        if self.thread and self.thread.is_alive():
            self._log("Connect ignored: network thread already running.")
            return
        self._stop_event.clear()
        port_list = [int(p) for p in (ports if ports is not None else network_ports())]
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(
            target=self._thread_entry,
            args=(host, tuple(port_list)),
            daemon=True,
        )
        self.thread.start()
        self._log(f"Connection thread started for host={host}, ports={port_list}.")

    def _thread_entry(self, host: str, ports: tuple[int, ...]) -> None:
        assert self.loop is not None
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._run(host, ports))
        except Exception as exc:
            self._log(f"Fatal network loop error: {exc!r}")
            self.incoming.put(make_message(ERROR, {"text": f"Network loop failed: {exc}"}))
        finally:
            self.ws = None
            if not self.loop.is_closed():
                self.loop.stop()
                self.loop.close()
            self.loop = None
            self.thread = None
            self._log("Network loop stopped.")

    async def _run(self, host: str, ports: tuple[int, ...]) -> None:
        last_error: Exception | None = None
        ws = None
        for port in ports:
            if self._stop_event.is_set():
                return
            uri = f"ws://{host}:{port}"
            self._log(f"Connecting to {uri} ...")
            try:
                ws = await websockets.connect(uri)
                self.connected_host = host
                self.connected_port = port
                self._log(f"Connected to {uri}.")
                self.incoming.put(
                    make_message(
                        CONNECTION_STATUS,
                        {"status": "connected", "host": host, "port": port},
                    )
                )
                break
            except Exception as exc:
                last_error = exc
                self._log(f"Connect failed to {uri}: {exc}")
        if ws is None:
            text = f"Failed to connect to {host} on ports {list(ports)}"
            if last_error is not None:
                text += f" ({last_error})"
            self.incoming.put(
                make_message(
                    CONNECTION_STATUS,
                    {"status": "failed", "host": host, "ports": list(ports), "error": text},
                )
            )
            return

        self.ws = ws
        try:
            await asyncio.gather(self._receiver(), self._sender())
        finally:
            if self.ws is not None:
                try:
                    await self.ws.close()
                except Exception:
                    pass
            self.incoming.put(
                make_message(
                    CONNECTION_STATUS,
                    {"status": "closed", "host": self.connected_host, "port": self.connected_port},
                )
            )

    async def _receiver(self) -> None:
        assert self.ws is not None
        try:
            async for message in self.ws:
                payload = decode(message)
                msg_type = str(payload.get("type", ""))
                if msg_type == ROLE:
                    role_value = payload.get("data", {}).get("role")
                    self.role = str(role_value) if role_value else None
                    self.is_my_turn = False
                elif msg_type == YOUR_TURN:
                    player = str(payload.get("data", {}).get("player", "") or "")
                    self.is_my_turn = bool(self.role and player and player == self.role)
                self._log(f"RX {msg_type}: {payload.get('data', {})}")
                self.incoming.put(payload)
        except websockets.exceptions.ConnectionClosed as exc:
            self._log(f"Receiver connection closed: {exc.code} {exc.reason}")
            self.incoming.put(make_message(ERROR, {"text": "Connection closed"}))
        except Exception as exc:
            self._log(f"Receiver error: {exc!r}")
            self.incoming.put(make_message(ERROR, {"text": f"Receiver error: {exc}"}))
        finally:
            self._stop_event.set()

    async def _sender(self) -> None:
        assert self.ws is not None
        while not self._stop_event.is_set():
            try:
                msg = self.outgoing.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.01)
                continue
            try:
                payload = encode(msg)
                await self.ws.send(payload)
                self._log(f"TX {msg.get('type', '?')}: {msg.get('data', {})}")
            except Exception as exc:
                self._log(f"Sender failed: {exc!r}")
                self.incoming.put(make_message(ERROR, {"text": f"Send failed: {exc}"}))
                self._stop_event.set()
                break

    def send(self, action_type: str, data: dict | None = None) -> None:
        msg = make_message(action_type, data or {})
        self.outgoing.put(msg)
        self._log(f"ENQUEUE {action_type}: {msg['data']}")

    def poll(self) -> list[dict]:
        messages: list[dict] = []
        while True:
            try:
                messages.append(self.incoming.get_nowait())
            except queue.Empty:
                break
        return messages

    def requeue_messages(self, messages: Iterable[dict]) -> None:
        for msg in messages:
            self.incoming.put(msg)

    def close(self) -> None:
        self._stop_event.set()
        close_future = None
        if self.loop is not None and self.ws is not None and not self.loop.is_closed():
            try:
                close_future = asyncio.run_coroutine_threadsafe(self.ws.close(), self.loop)
            except RuntimeError:
                close_future = None
        if close_future is not None:
            try:
                close_future.result(timeout=1.0)
            except Exception:
                pass
        if self.thread is not None and self.thread.is_alive() and threading.current_thread() is not self.thread:
            self.thread.join(timeout=1.0)
        self._log("Close requested.")
