"""Kiểm thử Giai đoạn 6: /cdc/tai-khoan (quản lý tài khoản, chỉ super_admin) — xem TASKS.md."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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

    import webapp.main as webapp_main
    return TestClient(webapp_main.app)


def _fresh_csrf(client: TestClient, path: str) -> str:
    client.get(path)
    return client.cookies.get("csrf_token", "")


def _login(client: TestClient, role: str = "super_admin", username: str = "cdc_user") -> None:
    client.get("/cdc/setup")
    csrf = client.cookies.get("csrf_token", "")
    client.post("/cdc/setup", data={
        "username": "sa_admin", "display_name": "Super", "password": "matkhau123",
        "password_confirm": "matkhau123", "csrf_token": csrf,
    })
    if role != "super_admin":
        core.create_cdc_account(username, "matkhau123", role=role, must_change_password=False, db_path=core.DB_PATH)
        csrf2 = _fresh_csrf(client, "/cdc/login")
        client.post("/cdc/login", data={"username": username, "password": "matkhau123", "csrf_token": csrf2})
    else:
        csrf2 = _fresh_csrf(client, "/cdc/login")
        client.post("/cdc/login", data={"username": "sa_admin", "password": "matkhau123", "csrf_token": csrf2})


def test_requires_super_admin(client: TestClient):
    _login(client, role=core.CDC_ROLE_ADMIN)
    resp = client.get("/cdc/tai-khoan")
    assert resp.status_code == 403


def test_super_admin_sees_list(client: TestClient):
    _login(client)
    resp = client.get("/cdc/tai-khoan")
    assert resp.status_code == 200 and "sa_admin" in resp.text


def test_create_account(client: TestClient):
    _login(client)
    csrf = _fresh_csrf(client, "/cdc/tai-khoan")
    resp = client.post("/cdc/tai-khoan/tao", data={
        "csrf_token": csrf, "username": "nguoi_moi", "display_name": "Người Mới",
        "role": core.CDC_ROLE_DATA_OPERATOR, "password": "matkhau123",
    }, follow_redirects=False)
    assert resp.status_code == 303
    accounts = core.list_cdc_accounts(db_path=core.DB_PATH)
    created = next(a for a in accounts if a["username"] == "nguoi_moi")
    assert created["role"] == core.CDC_ROLE_DATA_OPERATOR
    assert created["must_change_password"] == 1


def test_create_account_rejects_short_password(client: TestClient):
    _login(client)
    csrf = _fresh_csrf(client, "/cdc/tai-khoan")
    resp = client.post("/cdc/tai-khoan/tao", data={
        "csrf_token": csrf, "username": "nguoi_moi2", "role": core.CDC_ROLE_VIEWER, "password": "123",
    }, follow_redirects=False)
    assert resp.status_code == 303
    assert "err=" in resp.headers["location"]


def test_toggle_active_and_self_lock_guard(client: TestClient):
    _login(client)
    accounts = core.list_cdc_accounts(db_path=core.DB_PATH)
    self_id = next(a["id"] for a in accounts if a["username"] == "sa_admin")
    csrf = _fresh_csrf(client, "/cdc/tai-khoan")
    resp = client.post(f"/cdc/tai-khoan/{self_id}/kich-hoat", data={"csrf_token": csrf, "active": "0"}, follow_redirects=False)
    assert "err=" in resp.headers["location"]
    still = core.list_cdc_accounts(db_path=core.DB_PATH)
    assert next(a for a in still if a["id"] == self_id)["active"] == 1


def test_toggle_active_other_account(client: TestClient):
    _login(client)
    result = core.create_cdc_account("khoa_tk", "matkhau123", role=core.CDC_ROLE_VIEWER, db_path=core.DB_PATH)
    csrf = _fresh_csrf(client, "/cdc/tai-khoan")
    client.post(f"/cdc/tai-khoan/{result['id']}/kich-hoat", data={"csrf_token": csrf, "active": "0"})
    accounts = core.list_cdc_accounts(db_path=core.DB_PATH)
    assert next(a for a in accounts if a["id"] == result["id"])["active"] == 0


def test_change_role_self_guard(client: TestClient):
    _login(client)
    accounts = core.list_cdc_accounts(db_path=core.DB_PATH)
    self_id = next(a["id"] for a in accounts if a["username"] == "sa_admin")
    csrf = _fresh_csrf(client, "/cdc/tai-khoan")
    resp = client.post(f"/cdc/tai-khoan/{self_id}/vai-tro", data={"csrf_token": csrf, "role": core.CDC_ROLE_VIEWER}, follow_redirects=False)
    assert "err=" in resp.headers["location"]
    still = core.list_cdc_accounts(db_path=core.DB_PATH)
    assert next(a for a in still if a["id"] == self_id)["role"] == core.CDC_ROLE_SUPER_ADMIN


def test_change_role_other_account(client: TestClient):
    _login(client)
    result = core.create_cdc_account("doi_vt", "matkhau123", role=core.CDC_ROLE_VIEWER, db_path=core.DB_PATH)
    csrf = _fresh_csrf(client, "/cdc/tai-khoan")
    client.post(f"/cdc/tai-khoan/{result['id']}/vai-tro", data={"csrf_token": csrf, "role": core.CDC_ROLE_DATA_OPERATOR})
    accounts = core.list_cdc_accounts(db_path=core.DB_PATH)
    assert next(a for a in accounts if a["id"] == result["id"])["role"] == core.CDC_ROLE_DATA_OPERATOR


def test_reset_password(client: TestClient):
    _login(client)
    result = core.create_cdc_account("reset_tk", "matkhaucu12", role=core.CDC_ROLE_VIEWER,
                                      must_change_password=False, db_path=core.DB_PATH)
    csrf = _fresh_csrf(client, "/cdc/tai-khoan")
    resp = client.post(f"/cdc/tai-khoan/{result['id']}/dat-lai-mat-khau", data={
        "csrf_token": csrf, "new_password": "matkhaumoi99",
    }, follow_redirects=False)
    assert resp.status_code == 303
    verified = core.verify_cdc_account("reset_tk", "matkhaumoi99", db_path=core.DB_PATH)
    assert verified is not None and verified["must_change_password"]


def test_actions_require_csrf(client: TestClient):
    _login(client)
    resp = client.post("/cdc/tai-khoan/tao", data={
        "csrf_token": "sai", "username": "x", "role": core.CDC_ROLE_VIEWER, "password": "matkhau123",
    })
    assert resp.status_code == 403
