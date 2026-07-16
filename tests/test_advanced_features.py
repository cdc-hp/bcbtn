from __future__ import annotations

import json
import os
import socket
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from openpyxl import Workbook

import backup_manager
import core
import remote_core
from deployment_config import DeploymentConfig
from lan_discovery import DISCOVERY_MESSAGE, DiscoveryResponder
from lan_server import LanServerController


def make_excel(path: Path, fields, rows, sheet="Disease Cases"):
    wb = Workbook(); ws = wb.active; ws.title = sheet
    ws.append([label for label, _ in fields])
    for values in rows:
        ws.append([values.get(key, "") for _, key in fields])
    wb.save(path)


def configure_temp_backup(root: Path):
    core.BACKUP_DIR = root / "backups"
    backup_manager.LOCAL_BACKUP_DIR = root / "backups"
    backup_manager.CONFIG_PATH = root / "backup_policy.json"


def test_merge_to_trash_and_restore():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp); configure_temp_backup(root); db = root / "main.db"
        file = root / "cases.xlsx"
        base = {
            "full_name": "Nguyễn Văn A", "birth_date_raw": "01/01/1990", "gender": "Nam",
            "phone": "0901234567", "commune": "Phường Gia Viên",
            "main_diagnosis": "Sốt xuất huyết Dengue", "onset_date": "10/07/2026",
            "report_datetime": "11/07/2026 08:00", "reporting_unit": "Trạm Y tế",
        }
        make_excel(file, core.CASE_FIELDS, [dict(base, case_code="CA-1"), dict(base, case_code="CA-2", current_address="Gia Viên")])
        assert core.import_excel(file, db).inserted == 2
        group = core.find_duplicate_groups("case", db_path=db, min_score=60)[0]
        keep, remove = group["record_ids"][0], group["record_ids"][1:]
        result = core.merge_duplicate_records("case", keep, remove, {"phone": "0911111111", "full_name": "Nguyễn Văn A"}, db)
        assert result["removed_count"] == 1
        assert Path(result["backup_file"]).exists()
        kept = core.get_record("case", keep, db)
        assert kept["phone"] == "0911111111"
        assert core.dashboard_stats(db)["case_records"] == 1
        actions = core.list_duplicate_actions(db_path=db)
        assert actions[0]["pending_count"] == 1
        restored = core.restore_duplicate_action(result["action_id"], db)
        assert restored["restored_count"] == 1
        assert core.dashboard_stats(db)["case_records"] == 2
        assert core.list_duplicate_actions(db_path=db)[0]["pending_count"] == 0


def test_backup_verify_and_restore_database():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp); configure_temp_backup(root); db = root / "main.db"
        file = root / "outbreaks.xlsx"
        rows = [{"disease": "Sốt xuất huyết Dengue", "location": "Gia Viên", "first_onset_date": "10/07/2026", "case_count": 2, "report_datetime": "11/07/2026"}]
        make_excel(file, core.OUTBREAK_FIELDS, rows, "Danh sách ổ dịch")
        assert core.import_excel(file, db).inserted == 1
        policy = backup_manager.BackupPolicy(destination=str(root / "archive"), verify_after_backup=True)
        backup_manager.save_policy(policy)
        backup = backup_manager.create_backup(db, kind="manual", policy=policy)
        assert backup_manager.verify_backup(backup)["ok"]
        core.save_outbreak({"disease": "Sởi", "location": "Lê Chân", "first_onset_date": "12/07/2026"}, db_path=db)
        assert core.dashboard_stats(db)["outbreak_records"] == 2
        result = backup_manager.restore_backup(backup, db, policy)
        assert Path(result["safety_backup"]).exists()
        assert core.dashboard_stats(db)["outbreak_records"] == 1


def test_discovery_responder_unicast():
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); probe.bind(("127.0.0.1", 0)); discovery_port = probe.getsockname()[1]; probe.close()
    responder = DiscoveryResponder(9876, "GSBTN", "0.5.0", True, "CDC Server", discovery_port)
    responder.start()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); sock.settimeout(3)
    try:
        sock.sendto(DISCOVERY_MESSAGE, ("127.0.0.1", discovery_port))
        payload = json.loads(sock.recvfrom(8192)[0].decode("utf-8"))
        assert payload["server_name"] == "CDC Server"
        assert payload["url"].endswith(":9876")
        assert payload["password_required"] is True
    finally:
        sock.close(); responder.stop()


def test_lan_concurrent_clients_and_read_only_backup():
    with tempfile.TemporaryDirectory() as tmp:
        old_db, old_data = core.DB_PATH, core.DATA_DIR
        core.DATA_DIR = Path(tmp) / "data"; core.DB_PATH = core.DATA_DIR / "server.db"
        cfg = DeploymentConfig(mode="server", server_host="127.0.0.1", server_port=0, password="secret", discovery_enabled=False)
        controller = LanServerController(cfg)
        try:
            controller.start(); base = f"http://127.0.0.1:{controller.port}"
            def health(_):
                req = Request(base + "/health", headers={"X-GSBTN-Password": "secret"})
                with urlopen(req, timeout=5) as response:
                    return json.loads(response.read().decode("utf-8"))["ok"]
            with ThreadPoolExecutor(max_workers=8) as pool:
                assert all(pool.map(health, range(24)))

            def write_outbreak(index):
                payload = {
                    "function": "save_outbreak",
                    "args": [{"disease": "Sởi", "location": f"Điểm {index}", "first_onset_date": "12/07/2026"}],
                    "kwargs": {},
                }
                req = Request(base + "/rpc", data=json.dumps(payload).encode(), method="POST", headers={"Content-Type": "application/json", "X-GSBTN-Password": "secret"})
                with urlopen(req, timeout=15) as response:
                    return json.loads(response.read().decode("utf-8"))["ok"]

            with ThreadPoolExecutor(max_workers=6) as pool:
                assert all(pool.map(write_outbreak, range(12)))
            assert core.dashboard_stats(core.DB_PATH)["outbreak_records"] == 12
            status = controller.status()
            assert status["client_count"] >= 1
            assert sum(int(c["requests"]) for c in status["clients"]) >= 36
            assert any("save_outbreak" in str(item.get("path")) for item in status["logs"])
            controller.httpd.backup_in_progress = True
            body = json.dumps({"function": "save_outbreak", "args": [{"disease": "Sởi", "location": "Test"}], "kwargs": {}}).encode()
            req = Request(base + "/rpc", data=body, method="POST", headers={"Content-Type": "application/json", "X-GSBTN-Password": "secret"})
            try:
                urlopen(req, timeout=5)
                raise AssertionError("write during backup must fail")
            except HTTPError as exc:
                assert exc.code == 400
                assert "sao lưu" in exc.read().decode("utf-8")
        finally:
            controller.stop(); core.DB_PATH, core.DATA_DIR = old_db, old_data


def test_all_new_sources_compile():
    root = Path(__file__).parents[1]
    for name in ("app.py", "core.py", "deployment_config.py", "lan_server.py", "remote_core.py", "lan_discovery.py", "backup_manager.py", "duplicate_config.py"):
        compile((root / name).read_text(encoding="utf-8"), name, "exec")


def test_workstation_auto_reconnect_retries(monkeypatch):
    cfg = DeploymentConfig(
        mode="workstation", server_url="http://127.0.0.1:9999", auto_reconnect=True,
        reconnect_attempts=3, reconnect_delay_seconds=0.1,
    )
    calls = {"count": 0}

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return json.dumps({"ok": True, "app": "GSBTN", "version": "0.5.0"}).encode()

    def fake_urlopen(request, timeout=0):
        calls["count"] += 1
        if calls["count"] < 3:
            raise URLError("temporary network error")
        return Response()

    monkeypatch.setattr(remote_core, "load_config", lambda: cfg)
    monkeypatch.setattr(remote_core, "urlopen", fake_urlopen)
    monkeypatch.setattr(remote_core.time, "sleep", lambda _: None)
    assert remote_core.health()["app"] == "GSBTN"
    assert calls["count"] == 3
    assert remote_core.connection_status()["connected"] is True
