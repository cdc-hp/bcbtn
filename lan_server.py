from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import tempfile
import threading
from collections import deque
from dataclasses import asdict, is_dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import core
from deployment_config import DeploymentConfig, load_config
from lan_discovery import DiscoveryResponder, get_lan_ip

MAX_REQUEST_BYTES = 110 * 1024 * 1024
READ_FUNCTIONS = {
    "dashboard_stats", "disease_summary", "monthly_outbreak_summary", "recent_active_outbreaks",
    "list_filter_values", "query_records", "get_record", "list_quality_issues",
    "list_import_batches", "execute_select", "find_duplicate_groups", "list_duplicate_actions",
    "list_backups",
}
WRITE_FUNCTIONS = {
    "save_outbreak", "delete_record", "remove_duplicate_records", "merge_duplicate_records",
    "restore_duplicate_action", "create_backup",
}

DB_FUNCTIONS = {
    "dashboard_stats", "disease_summary", "monthly_outbreak_summary", "recent_active_outbreaks",
    "list_filter_values", "query_records", "get_record", "save_outbreak", "delete_record",
    "list_quality_issues", "list_import_batches", "execute_select", "find_duplicate_groups",
    "remove_duplicate_records", "merge_duplicate_records", "list_duplicate_actions",
    "restore_duplicate_action", "create_backup",
}


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def port_available(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, int(port)))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def configure_windows_firewall(port: int) -> dict[str, Any]:
    if os.name != "nt":
        return {"ok": False, "message": "Chỉ cấu hình Windows Firewall trên Windows."}
    rule_tcp = f"GSBTN Server TCP {int(port)}"
    rule_udp = "GSBTN Discovery UDP 8766"
    commands = [
        f'netsh advfirewall firewall delete rule name="{rule_tcp}"',
        f'netsh advfirewall firewall add rule name="{rule_tcp}" dir=in action=allow protocol=TCP localport={int(port)} profile=private',
        f'netsh advfirewall firewall delete rule name="{rule_udp}"',
        f'netsh advfirewall firewall add rule name="{rule_udp}" dir=in action=allow protocol=UDP localport=8766 profile=private',
    ]
    script = "; ".join(f"& {command}" for command in commands)
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=60,
        )
        if completed.returncode == 0:
            return {"ok": True, "message": "Đã tạo quy tắc tường lửa cho mạng Riêng tư."}
        return {"ok": False, "message": (completed.stderr or completed.stdout or "Cần chạy ứng dụng bằng quyền quản trị.").strip()}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


class ApiServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], config: DeploymentConfig):
        super().__init__(address, ApiHandler)
        self.config = config
        self.clients: dict[str, dict[str, Any]] = {}
        self.request_log: deque[dict[str, Any]] = deque(maxlen=500)
        self.backup_in_progress = False
        self.state_lock = threading.RLock()

    def register_request(self, client_ip: str, path: str, method: str, ok: bool = True) -> None:
        now = datetime.now().isoformat(sep=" ", timespec="seconds")
        with self.state_lock:
            client = self.clients.setdefault(client_ip, {"ip": client_ip, "first_seen": now, "requests": 0})
            client["last_seen"] = now
            client["requests"] = int(client.get("requests", 0)) + 1
            client["last_path"] = path
            self.request_log.appendleft({"time": now, "ip": client_ip, "method": method, "path": path, "ok": ok})

    def status_payload(self) -> dict[str, Any]:
        with self.state_lock:
            clients = sorted(self.clients.values(), key=lambda item: str(item.get("last_seen", "")), reverse=True)
            logs = list(self.request_log)[:100]
        return {
            "running": True,
            "address": f"http://{get_lan_ip()}:{self.server_port}",
            "port": self.server_port,
            "server_name": self.config.server_name or socket.gethostname(),
            "password_required": bool(self.config.password),
            "backup_in_progress": self.backup_in_progress,
            "client_count": len(clients),
            "clients": clients,
            "logs": logs,
        }


class ApiHandler(BaseHTTPRequestHandler):
    server: ApiServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    @property
    def client_ip(self) -> str:
        return str(self.client_address[0])

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(_jsonable(payload), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        expected = self.server.config.password
        return not expected or self.headers.get("X-GSBTN-Password", "") == expected

    def _reject_auth(self) -> None:
        self.server.register_request(self.client_ip, self.path, self.command, False)
        self._write_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "Sai mật khẩu máy chủ."})

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorized():
            self._reject_auth(); return
        path = self.path.rstrip("/")
        if path == "/health":
            payload = {
                "ok": True, "app": core.APP_NAME, "version": core.VERSION, "mode": "server",
                "server_name": self.server.config.server_name or socket.gethostname(),
                "lan_ip": get_lan_ip(), "port": self.server.server_port,
                "password_required": bool(self.server.config.password),
                "read_only": self.server.backup_in_progress,
            }
        elif path == "/status":
            payload = {"ok": True, "result": self.server.status_payload()}
        else:
            self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Không tìm thấy endpoint."}); return
        self.server.register_request(self.client_ip, path, "GET", True)
        self._write_json(HTTPStatus.OK, payload)

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            self._reject_auth(); return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_REQUEST_BYTES:
            self._write_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"ok": False, "error": "Yêu cầu vượt giới hạn 110 MB."})
            return
        path = self.path.rstrip("/")
        try:
            payload = json.loads((self.rfile.read(length) if length else b"{}").decode("utf-8"))
            log_path = path
            if path == "/rpc":
                log_path = f"/rpc:{str(payload.get('function', 'unknown'))}"
                result = self._handle_rpc(payload)
            elif path == "/import":
                if self.server.backup_in_progress:
                    raise RuntimeError("Máy chủ đang sao lưu; tạm thời chỉ cho phép đọc dữ liệu.")
                result = self._handle_import(payload)
            else:
                self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Không tìm thấy endpoint."}); return
            self.server.register_request(self.client_ip, log_path, "POST", True)
            self._write_json(HTTPStatus.OK, {"ok": True, "result": result})
        except Exception as exc:
            self.server.register_request(self.client_ip, locals().get("log_path", path), "POST", False)
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

    def _handle_rpc(self, payload: dict[str, Any]) -> Any:
        function_name = str(payload.get("function", ""))
        if function_name not in READ_FUNCTIONS | WRITE_FUNCTIONS:
            raise ValueError("Hàm RPC không được phép.")
        args, kwargs = payload.get("args") or [], payload.get("kwargs") or {}
        if not isinstance(args, list) or not isinstance(kwargs, dict):
            raise ValueError("args/kwargs không hợp lệ.")
        kwargs.pop("db_path", None)
        if function_name in DB_FUNCTIONS:
            kwargs["db_path"] = core.DB_PATH
        if function_name in WRITE_FUNCTIONS and function_name != "create_backup" and self.server.backup_in_progress:
            raise RuntimeError("Máy chủ đang sao lưu; tạm thời chỉ cho phép đọc dữ liệu.")
        function = getattr(core, function_name, None)
        if not callable(function):
            raise ValueError(f"Máy chủ chưa hỗ trợ hàm {function_name}.")
        if function_name == "create_backup":
            with self.server.state_lock:
                if self.server.backup_in_progress:
                    raise RuntimeError("Máy chủ đang thực hiện một bản sao lưu khác.")
                self.server.backup_in_progress = True
            try:
                return function(*args, **kwargs)
            finally:
                with self.server.state_lock:
                    self.server.backup_in_progress = False
        return function(*args, **kwargs)

    def _handle_import(self, payload: dict[str, Any]) -> Any:
        name = Path(str(payload.get("file_name", "du_lieu.xlsx"))).name
        content = payload.get("content_base64")
        if not isinstance(content, str) or not content:
            raise ValueError("Thiếu nội dung file Excel.")
        if Path(name).suffix.lower() not in {".xlsx", ".xlsm"}:
            raise ValueError("Chỉ chấp nhận file XLSX hoặc XLSM.")
        data = base64.b64decode(content.encode("ascii"), validate=True)
        if len(data) > 100 * 1024 * 1024:
            raise ValueError("File vượt quá giới hạn 100 MB.")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / name
            path.write_bytes(data)
            return core.import_excel(path, core.DB_PATH)


class LanServerController:
    def __init__(self, config: DeploymentConfig | None = None):
        self.config = config or load_config()
        self.httpd: ApiServer | None = None
        self.thread: threading.Thread | None = None
        self.discovery: DiscoveryResponder | None = None
        self.last_error = ""

    @property
    def running(self) -> bool:
        return bool(self.httpd and self.thread and self.thread.is_alive())

    @property
    def port(self) -> int:
        return int(self.httpd.server_port if self.httpd else self.config.server_port)

    @property
    def address(self) -> str:
        return f"http://{get_lan_ip()}:{self.port}"

    def start(self) -> str:
        if self.running:
            return self.address
        core.init_db()
        if not port_available(self.config.server_host, self.config.server_port):
            raise OSError(f"Cổng {self.config.server_port} đang được chương trình khác sử dụng.")
        try:
            self.httpd = ApiServer((self.config.server_host, self.config.server_port), self.config)
            self.thread = threading.Thread(target=self.httpd.serve_forever, name="GSBTN-LAN-Server", daemon=True)
            self.thread.start()
            self.last_error = ""
            if self.config.discovery_enabled:
                self.discovery = DiscoveryResponder(
                    self.port, core.APP_NAME, core.VERSION, bool(self.config.password), self.config.server_name
                )
                try:
                    self.discovery.start()
                except OSError as exc:
                    self.last_error = f"Server chạy nhưng không mở được tự dò LAN: {exc}"
            return self.address
        except Exception as exc:
            self.httpd = None; self.thread = None; self.last_error = str(exc)
            raise

    def stop(self) -> None:
        if self.discovery:
            self.discovery.stop()
        self.discovery = None
        if self.httpd:
            self.httpd.shutdown(); self.httpd.server_close()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3)
        self.httpd = None; self.thread = None

    def status(self) -> dict[str, Any]:
        if self.httpd:
            payload = self.httpd.status_payload()
            payload["discovery_running"] = bool(self.discovery and self.discovery.running)
            payload["last_error"] = self.last_error
            return payload
        return {
            "running": False, "address": self.address, "port": self.config.server_port,
            "server_name": self.config.server_name or socket.gethostname(),
            "password_required": bool(self.config.password), "backup_in_progress": False,
            "client_count": 0, "clients": [], "logs": [], "discovery_running": False,
            "last_error": self.last_error,
        }
