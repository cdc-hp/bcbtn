"""Kiểm thử Giai đoạn 6: /cdc/sao-luu (sao lưu/phục hồi CSDL qua Web) — xem TASKS.md."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backup_manager
import core
import deployment_config


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(core, "DATA_DIR", tmp_path / "data")
    core.DATA_DIR.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(core, "DB_PATH", core.DATA_DIR / "test.db")
    monkeypatch.setattr(core, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(core, "QUEUE_DIR", tmp_path / "queue")
    monkeypatch.setattr(deployment_config, "CONFIG_PATH", tmp_path / "deployment.json")
    monkeypatch.setattr(backup_manager, "CONFIG_PATH", tmp_path / "backup_policy.json")
    monkeypatch.setattr(backup_manager, "LOCAL_BACKUP_DIR", tmp_path / "backups")

    import webapp.main as webapp_main
    return TestClient(webapp_main.app)


def _fresh_csrf(client: TestClient, path: str) -> str:
    client.get(path)
    return client.cookies.get("csrf_token", "")


def _login(client: TestClient, role: str = "admin") -> None:
    client.get("/cdc/setup")
    csrf = client.cookies.get("csrf_token", "")
    client.post("/cdc/setup", data={
        "username": "sa_admin", "display_name": "Super", "password": "matkhau123",
        "password_confirm": "matkhau123", "csrf_token": csrf,
    })
    if role != "super_admin":
        core.create_cdc_account("cdc_user", "matkhau123", role=role, must_change_password=False, db_path=core.DB_PATH)
        csrf2 = _fresh_csrf(client, "/cdc/login")
        client.post("/cdc/login", data={"username": "cdc_user", "password": "matkhau123", "csrf_token": csrf2})
    else:
        csrf2 = _fresh_csrf(client, "/cdc/login")
        client.post("/cdc/login", data={"username": "sa_admin", "password": "matkhau123", "csrf_token": csrf2})


def test_requires_admin_or_super_admin(client: TestClient):
    _login(client, role=core.CDC_ROLE_DATA_OPERATOR)
    resp = client.get("/cdc/sao-luu")
    assert resp.status_code == 403


def test_admin_can_view_and_create_backup(client: TestClient):
    _login(client, role=core.CDC_ROLE_ADMIN)
    resp = client.get("/cdc/sao-luu")
    assert resp.status_code == 200

    csrf = _fresh_csrf(client, "/cdc/sao-luu")
    resp = client.post("/cdc/sao-luu/tao", data={"csrf_token": csrf}, follow_redirects=False)
    assert resp.status_code == 303
    backups = backup_manager.list_backups()
    assert len(backups) == 1


def test_admin_cannot_see_restore_button(client: TestClient):
    _login(client, role=core.CDC_ROLE_ADMIN)
    core.create_backup(core.DB_PATH)
    resp = client.get("/cdc/sao-luu")
    assert "Phục hồi</button>" not in resp.text


def test_download_backup(client: TestClient):
    _login(client)
    core.create_backup(core.DB_PATH)
    name = backup_manager.list_backups()[0]["name"]
    resp = client.get(f"/cdc/sao-luu/{name}/tai-ve")
    assert resp.status_code == 200
    assert len(resp.content) > 0


def test_download_rejects_path_traversal(client: TestClient):
    _login(client)
    core.create_backup(core.DB_PATH)
    resp = client.get("/cdc/sao-luu/..%2F..%2Fwindows%2Fwin.ini/tai-ve")
    assert resp.status_code in (403, 404)


def test_admin_cannot_restore(client: TestClient):
    _login(client, role=core.CDC_ROLE_ADMIN)
    core.create_backup(core.DB_PATH)
    name = backup_manager.list_backups()[0]["name"]
    csrf = _fresh_csrf(client, "/cdc/sao-luu")
    resp = client.post(f"/cdc/sao-luu/{name}/phuc-hoi", data={"csrf_token": csrf})
    assert resp.status_code == 403


def test_super_admin_can_restore(client: TestClient, tmp_path: Path):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    core.create_cdc_account("truoc_phuc_hoi", "matkhau123", role=core.CDC_ROLE_VIEWER, db_path=core.DB_PATH)
    core.create_backup(core.DB_PATH)
    core.create_cdc_account("sau_phuc_hoi", "matkhau123", role=core.CDC_ROLE_VIEWER, db_path=core.DB_PATH)
    name = backup_manager.list_backups()[0]["name"]

    csrf = _fresh_csrf(client, "/cdc/sao-luu")
    resp = client.post(f"/cdc/sao-luu/{name}/phuc-hoi", data={"csrf_token": csrf}, follow_redirects=False)
    assert resp.status_code == 303
    usernames = {a["username"] for a in core.list_cdc_accounts(db_path=core.DB_PATH)}
    assert "truoc_phuc_hoi" in usernames
    assert "sau_phuc_hoi" not in usernames

    actions = core.list_audit_log(db_path=core.DB_PATH)
    assert any(a["action"] == "restore_backup_web" for a in actions)


def test_save_policy_requires_super_admin(client: TestClient):
    _login(client, role=core.CDC_ROLE_ADMIN)
    csrf = _fresh_csrf(client, "/cdc/sao-luu")
    resp = client.post("/cdc/sao-luu/chinh-sach", data={
        "csrf_token": csrf, "interval_hours": "12", "keep_daily": "5", "keep_weekly": "4",
        "keep_monthly": "3", "keep_manual": "10",
    })
    assert resp.status_code == 403


def test_save_policy(client: TestClient):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    csrf = _fresh_csrf(client, "/cdc/sao-luu")
    resp = client.post("/cdc/sao-luu/chinh-sach", data={
        "csrf_token": csrf, "enabled": "1", "interval_hours": "12", "keep_daily": "5",
        "keep_weekly": "4", "keep_monthly": "3", "keep_manual": "10", "verify_after_backup": "1",
    }, follow_redirects=False)
    assert resp.status_code == 303
    saved = backup_manager.load_policy()
    assert saved.interval_hours == 12 and saved.keep_daily == 5
