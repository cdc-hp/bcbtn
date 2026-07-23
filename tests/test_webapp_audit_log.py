"""Kiểm thử Giai đoạn 6: /cdc/nhat-ky (xem/lọc nhật ký thao tác) — xem TASKS.md."""

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
    _login(client, role=core.CDC_ROLE_VIEWER)
    resp = client.get("/cdc/nhat-ky")
    assert resp.status_code == 403


def test_data_operator_also_forbidden(client: TestClient):
    _login(client, role=core.CDC_ROLE_DATA_OPERATOR)
    resp = client.get("/cdc/nhat-ky")
    assert resp.status_code == 403


def test_shows_login_events(client: TestClient):
    _login(client)
    resp = client.get("/cdc/nhat-ky")
    assert resp.status_code == 200
    assert "login" in resp.text
    assert "sa_admin" in resp.text


def test_filter_by_action(client: TestClient):
    _login(client)
    core.log_audit("thao_tac_thu", actor="sa_admin", db_path=core.DB_PATH)
    resp = client.get("/cdc/nhat-ky", params={"action": "thao_tac_thu"})
    assert resp.status_code == 200
    assert "thao_tac_thu" in resp.text
    assert "<td>login</td>" not in resp.text


def test_filter_by_actor_no_match(client: TestClient):
    _login(client)
    resp = client.get("/cdc/nhat-ky", params={"actor": "khong_ton_tai"})
    assert "Không có dòng nhật ký" in resp.text
