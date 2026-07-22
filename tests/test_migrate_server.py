from __future__ import annotations

import json
import tempfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import core
import lan_server as lan_server_module
from deployment_config import DeploymentConfig
from lan_server import LanServerController


def get(addr: str, path: str) -> dict:
    req = Request(addr + path, method="GET")
    try:
        return json.loads(urlopen(req, timeout=10).read().decode())
    except HTTPError as exc:
        return json.loads(exc.read().decode())


def post(addr: str, path: str, payload: dict, password: str | None = None) -> dict:
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if password is not None:
        headers["X-GSBTN-Password"] = password
    req = Request(addr + path, data=body, headers=headers, method="POST")
    try:
        return json.loads(urlopen(req, timeout=10).read().decode())
    except HTTPError as exc:
        return json.loads(exc.read().decode())


def test_receive_full_backup_refuses_overwrite_without_force():
    """Máy chủ MỚI phải từ chối nhận 1 bản sao lưu đầy đủ nếu đã có dữ liệu thật, trừ khi
    force=true — lớp bảo vệ chống ghi đè nhầm một máy chủ đang hoạt động."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        core.DATA_DIR = root / "data"; core.DATA_DIR.mkdir()
        core.DB_PATH = core.DATA_DIR / "test.db"
        core.BACKUP_DIR = root / "backups"; core.QUEUE_DIR = root / "queue"
        cfg = DeploymentConfig(mode="server", server_host="127.0.0.1", server_port=0, password="")
        ctrl = LanServerController(cfg)
        ctrl.start()
        addr = f"http://127.0.0.1:{ctrl.port}"
        try:
            fake_backup_b64 = _base64_empty_sqlite()

            # Máy còn trống (chỉ mới init_db(), chưa có dữ liệu thật) -> chấp nhận dù force=False.
            first = post(addr, "/admin/receive-full-backup", {"content_base64": fake_backup_b64, "force": False})
            assert first["ok"], first

            created = post(
                addr, "/rpc",
                {"function": "create_commune_account", "args": ["Xã Đã Có", "daco", "matkhau123", ""], "kwargs": {}},
            )
            assert created["ok"], created

            second = post(addr, "/admin/receive-full-backup", {"content_base64": fake_backup_b64, "force": False})
            assert second["ok"] is False
            assert "đã có dữ liệu" in second["error"]

            forced = post(addr, "/admin/receive-full-backup", {"content_base64": fake_backup_b64, "force": True})
            assert forced["ok"], forced
        finally:
            ctrl.stop()


def test_migrate_to_new_server_retires_old_server_and_blocks_all_requests(monkeypatch):
    """migrate_to_new_server(): tạo bản sao lưu, gửi sang máy mới (mock — máy mới là 1 tiến
    trình/máy khác trong thực tế, không mô phỏng lại ở đây vì core.DB_PATH là biến toàn cục theo
    tiến trình), rồi ĐÓNG máy chủ này. Sau khi đóng, MỌI request (kể cả không xác thực, kể cả
    trước đây có mật khẩu đúng) đều phải nhận được thông báo "đã chuyển máy chủ" thay vì dữ liệu
    thật — đây là phần quan trọng nhất cần đảm bảo (tránh 2 máy cùng phục vụ dữ liệu song song)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        core.DATA_DIR = root / "data"; core.DATA_DIR.mkdir()
        core.DB_PATH = core.DATA_DIR / "test.db"
        core.BACKUP_DIR = root / "backups"; core.QUEUE_DIR = root / "queue"
        core.create_commune_account("Xã Gia Viên", "xagiavien", "matkhau123", db_path=core.DB_PATH)

        cfg = DeploymentConfig(mode="server", server_host="127.0.0.1", server_port=0, password="matkhaucu")
        ctrl = LanServerController(cfg)
        ctrl.start()
        addr = f"http://127.0.0.1:{ctrl.port}"
        try:
            sent = {}

            class _FakeResponse:
                def __init__(self, body: bytes):
                    self._body = body

                def read(self) -> bytes:
                    return self._body

                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

            def fake_urlopen(request, timeout=None):
                sent["url"] = request.full_url
                sent["body"] = json.loads(request.data.decode("utf-8"))
                return _FakeResponse(json.dumps({"ok": True, "result": {"restored": True}}).encode("utf-8"))

            monkeypatch.setattr(lan_server_module, "urlopen", fake_urlopen)

            # Trước khi chuyển: máy chủ phục vụ dữ liệu bình thường.
            before = post(addr, "/rpc", {"function": "list_commune_accounts", "args": [], "kwargs": {}}, password="matkhaucu")
            assert before["ok"] and len(before["result"]) == 1

            result = ctrl.migrate_to_new_server("http://may-chu-moi.vi-du:8765", new_server_password="matkhaumoi")
            assert result["new_server_url"] == "http://may-chu-moi.vi-du:8765"
            assert sent["url"] == "http://may-chu-moi.vi-du:8765/admin/receive-full-backup"
            assert sent["body"]["content_base64"]  # đã gửi kèm nội dung sao lưu thật

            # Sau khi chuyển: MỌI request đều bị chặn và báo địa chỉ mới — kể cả dùng đúng mật
            # khẩu cũ, kể cả không gửi mật khẩu nào.
            after_with_password = post(
                addr, "/rpc", {"function": "list_commune_accounts", "args": [], "kwargs": {}}, password="matkhaucu",
            )
            assert after_with_password["ok"] is False
            assert after_with_password.get("retired") is True
            assert after_with_password["new_server_url"] == "http://may-chu-moi.vi-du:8765"

            after_no_auth = get(addr, "/health")
            assert after_no_auth["ok"] is False and after_no_auth["retired"] is True

            after_public_page = get(addr, "/xa")
            assert isinstance(after_public_page, dict) and after_public_page.get("retired") is True
        finally:
            ctrl.stop()


def _base64_empty_sqlite() -> str:
    import base64
    import sqlite3
    import tempfile as _tempfile

    with _tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "empty.db"
        # sqlite3.connect(...).close() một mình không chắc đã ghi byte nào xuống đĩa (SQLite trì
        # hoãn tạo file tới khi có thao tác ghi thật) -> chạy 1 lệnh DDL để buộc file có nội dung.
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.commit()
        conn.close()
        return base64.b64encode(db_path.read_bytes()).decode("ascii")
