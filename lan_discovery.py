from __future__ import annotations

import json
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any

DISCOVERY_PORT = 8766
DISCOVERY_MESSAGE = b"GSBTN_DISCOVER_V1"


def get_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


@dataclass
class DiscoveryResponder:
    server_port: int
    app_name: str
    version: str
    password_required: bool
    server_name: str = ""
    discovery_port: int = DISCOVERY_PORT

    def __post_init__(self):
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", self.discovery_port))
        sock.settimeout(1.0)
        self._socket = sock
        self._stopping.clear()
        self._thread = threading.Thread(target=self._serve, name="GSBTN-Discovery", daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        assert self._socket is not None
        while not self._stopping.is_set():
            try:
                data, address = self._socket.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            if data.strip() != DISCOVERY_MESSAGE:
                continue
            payload = {
                "protocol": 1,
                "app": self.app_name,
                "version": self.version,
                "server_name": self.server_name or socket.gethostname(),
                "url": f"http://{get_lan_ip()}:{self.server_port}",
                "password_required": self.password_required,
            }
            try:
                self._socket.sendto(json.dumps(payload, ensure_ascii=False).encode("utf-8"), address)
            except OSError:
                pass

    def stop(self) -> None:
        self._stopping.set()
        if self._socket:
            self._socket.close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._socket = None
        self._thread = None


def discover_servers(timeout: float = 1.5, discovery_port: int = DISCOVERY_PORT) -> list[dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.2)
    sock.bind(("", 0))
    try:
        for target in ("255.255.255.255", "<broadcast>"):
            try:
                sock.sendto(DISCOVERY_MESSAGE, (target, discovery_port))
            except OSError:
                pass
        deadline = time.monotonic() + max(0.2, timeout)
        while time.monotonic() < deadline:
            try:
                data, address = sock.recvfrom(8192)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                payload = json.loads(data.decode("utf-8"))
            except Exception:
                continue
            url = str(payload.get("url") or "").rstrip("/")
            if not url:
                continue
            payload["source_ip"] = address[0]
            results[url] = payload
    finally:
        sock.close()
    return sorted(results.values(), key=lambda item: (str(item.get("server_name", "")), str(item.get("url", ""))))
