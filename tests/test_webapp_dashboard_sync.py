"""Kiểm thử Giai đoạn 7: nút "Đồng bộ ngay" + trạng thái đồng bộ trên /cdc/dashboard, và
/health phản ánh trạng thái tác vụ nền thật (xem TASKS.md)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import core
import deployment_config
import secondary_sync
from webapp import scheduler


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(core, "DATA_DIR", tmp_path / "data")
    core.DATA_DIR.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(core, "DB_PATH", core.DATA_DIR / "test.db")
    monkeypatch.setattr(core, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(core, "QUEUE_DIR", tmp_path / "queue")
    monkeypatch.setattr(deployment_config, "CONFIG_PATH", tmp_path / "deployment.json")

    scheduler._state.update({
        "running": False, "last_run_at": "", "last_success_at": "", "last_result": None, "last_error": "",
    })

    import webapp.main as webapp_main
    return TestClient(webapp_main.app)


@pytest.fixture(autouse=True)
def _cleanup_scheduler():
    yield
    scheduler.shutdown()
    if scheduler._run_lock.locked():
        scheduler._run_lock.release()


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


def test_health_reports_scheduler_not_running_without_lifespan(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["scheduler"] == "chua_chay"


def test_dashboard_shows_unconfigured_message(client: TestClient):
    _login(client)
    resp = client.get("/cdc/dashboard")
    assert resp.status_code == 200
    assert "Chưa cấu hình máy chủ phụ" in resp.text
    assert "Đồng bộ ngay" not in resp.text


def test_viewer_does_not_see_sync_button(client: TestClient):
    _login(client, role=core.CDC_ROLE_VIEWER)
    config = deployment_config.load_config()
    config.secondary_webapp_url = "https://example.com/exec"
    config.secondary_shared_key = "khoa"
    deployment_config.save_config(config)
    resp = client.get("/cdc/dashboard")
    assert "Đồng bộ ngay" not in resp.text


def test_sync_now_triggers_pull_and_updates_dashboard(client: TestClient, monkeypatch):
    _login(client)
    config = deployment_config.load_config()
    config.secondary_webapp_url = "https://example.com/exec"
    config.secondary_shared_key = "khoa"
    deployment_config.save_config(config)
    monkeypatch.setattr(
        secondary_sync, "pull_secondary_queue",
        lambda url, key, db_path=None, timeout=30: {"pending_count": 3, "pulled_count": 3, "errors": []},
    )

    csrf = _fresh_csrf(client, "/cdc/dashboard")
    resp = client.post("/cdc/dashboard/dong-bo-may-chu-phu", data={"csrf_token": csrf}, follow_redirects=False)
    assert resp.status_code == 303

    dashboard = client.get("/cdc/dashboard")
    assert "kéo 3/3 mục" in dashboard.text


def test_sync_now_requires_role(client: TestClient):
    _login(client, role=core.CDC_ROLE_VIEWER)
    csrf = _fresh_csrf(client, "/cdc/dashboard")
    resp = client.post("/cdc/dashboard/dong-bo-may-chu-phu", data={"csrf_token": csrf})
    assert resp.status_code == 403


def test_sync_now_requires_csrf(client: TestClient):
    _login(client)
    resp = client.post("/cdc/dashboard/dong-bo-may-chu-phu", data={"csrf_token": "sai"})
    assert resp.status_code == 403
