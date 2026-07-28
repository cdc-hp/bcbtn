"""Kiểm thử Giai đoạn 8: /cdc/cau-hinh (cấu hình triển khai qua Web, chỉ super_admin) — xem
TASKS.md."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backup_manager
import core
import deployment_config
import update_manager
from webapp.services import web_update


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(core, "DATA_DIR", tmp_path / "data")
    core.DATA_DIR.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(core, "DB_PATH", core.DATA_DIR / "test.db")
    monkeypatch.setattr(core, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(core, "QUEUE_DIR", tmp_path / "queue")
    monkeypatch.setattr(core, "UPDATE_CACHE_DIR", tmp_path / "update_cache")
    monkeypatch.setattr(deployment_config, "CONFIG_PATH", tmp_path / "deployment.json")
    monkeypatch.setattr(backup_manager, "CONFIG_PATH", tmp_path / "backup_policy.json")
    monkeypatch.setattr(backup_manager, "LOCAL_BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(web_update, "_job_running", False)

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


def test_requires_super_admin(client: TestClient):
    _login(client, role=core.CDC_ROLE_ADMIN)
    resp = client.get("/cdc/cau-hinh")
    assert resp.status_code == 403


def test_super_admin_sees_settings_page(client: TestClient):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    resp = client.get("/cdc/cau-hinh")
    assert resp.status_code == 200
    assert "Cấu hình triển khai" in resp.text
    assert "Chưa cài đặt làm dịch vụ Windows" in resp.text or "Chưa cài đặt dịch vụ Windows" in resp.text
    assert "Cập nhật ứng dụng" in resp.text
    assert f"v{core.VERSION}" in resp.text
    assert "/cdc/cau-hinh/cap-nhat/kiem-tra" in resp.text


def test_secret_not_echoed_in_page(client: TestClient):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    config = deployment_config.load_config()
    config.gas_api_key = "khoa-bi-mat-that-su"
    config.secondary_shared_key = "khoa-dong-bo-bi-mat"
    deployment_config.save_config(config)
    resp = client.get("/cdc/cau-hinh")
    assert "khoa-bi-mat-that-su" not in resp.text
    assert "khoa-dong-bo-bi-mat" not in resp.text


def test_save_updates_config_and_backup_policy(client: TestClient):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    csrf = _fresh_csrf(client, "/cdc/cau-hinh")
    resp = client.post("/cdc/cau-hinh", data={
        "csrf_token": csrf, "server_host": "127.0.0.1", "server_port": "9001",
        "public_url": "https://cdc-hp.io.vn", "gas_api_key": "khoa-moi",
        "secondary_webapp_url": "https://script.google.com/macros/s/xyz/exec",
        "secondary_shared_key": "khoa-dong-bo-moi", "secondary_sync_interval_minutes": "45",
        "backup_destination": str((Path(core.BACKUP_DIR).parent / "sao_luu_rieng")),
    }, follow_redirects=False)
    assert resp.status_code == 303
    assert "Đổi cổng" in resp.headers["location"] or "%C4%90%E1%BB%95i%20c%E1%BB%95ng" in resp.headers["location"]

    saved = deployment_config.load_config()
    assert saved.server_host == "127.0.0.1"
    assert saved.server_port == 9001
    assert saved.public_url == "https://cdc-hp.io.vn"
    assert saved.gas_api_key == "khoa-moi"
    assert saved.secondary_webapp_url == "https://script.google.com/macros/s/xyz/exec"
    assert saved.secondary_shared_key == "khoa-dong-bo-moi"
    assert saved.secondary_sync_interval_minutes == 45

    policy = backup_manager.load_policy()
    assert policy.destination.endswith("sao_luu_rieng")

    actions = core.list_audit_log(db_path=core.DB_PATH)
    assert any(a["action"] == "save_deployment_settings_web" for a in actions)


def test_save_blank_secret_keeps_existing_value(client: TestClient):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    config = deployment_config.load_config()
    config.gas_api_key = "khoa-cu-giu-nguyen"
    deployment_config.save_config(config)

    csrf = _fresh_csrf(client, "/cdc/cau-hinh")
    client.post("/cdc/cau-hinh", data={
        "csrf_token": csrf, "server_host": "0.0.0.0", "server_port": "8765",
        "public_url": "", "gas_api_key": "", "secondary_webapp_url": "",
        "secondary_shared_key": "", "secondary_sync_interval_minutes": "20", "backup_destination": "",
    })
    saved = deployment_config.load_config()
    assert saved.gas_api_key == "khoa-cu-giu-nguyen"


def test_save_requires_csrf(client: TestClient):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    resp = client.post("/cdc/cau-hinh", data={
        "csrf_token": "sai", "server_host": "0.0.0.0", "server_port": "8765",
    })
    assert resp.status_code == 403


def test_save_requires_super_admin(client: TestClient):
    _login(client, role=core.CDC_ROLE_DATA_OPERATOR)
    csrf = _fresh_csrf(client, "/cdc/dashboard")
    resp = client.post("/cdc/cau-hinh", data={
        "csrf_token": csrf, "server_host": "0.0.0.0", "server_port": "8765",
    })
    assert resp.status_code == 403


def test_restart_fails_gracefully_when_not_installed(client: TestClient):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    csrf = _fresh_csrf(client, "/cdc/cau-hinh")
    resp = client.post("/cdc/cau-hinh/khoi-dong-lai", data={"csrf_token": csrf}, follow_redirects=False)
    assert resp.status_code == 303
    assert "err=" in resp.headers["location"]

    actions = core.list_audit_log(db_path=core.DB_PATH)
    assert any(a["action"] == "restart_service_web_failed" for a in actions)


def test_restart_requires_super_admin(client: TestClient):
    _login(client, role=core.CDC_ROLE_ADMIN)
    csrf = _fresh_csrf(client, "/cdc/dashboard")
    resp = client.post("/cdc/cau-hinh/khoi-dong-lai", data={"csrf_token": csrf})
    assert resp.status_code == 403


def _new_release(*, sha256: str = "a" * 64) -> update_manager.GithubReleaseInfo:
    return update_manager.GithubReleaseInfo(
        version="9.9.9",
        notes="Bổ sung cơ chế cập nhật trên trình duyệt.",
        asset_name="CDC-GiamSatDichBenh-Server-Setup-v9.9.9.exe",
        download_url="https://example.test/web-server.exe",
        sha256=sha256,
    )


def test_super_admin_can_check_web_update(client: TestClient, monkeypatch):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    monkeypatch.setattr(update_manager, "fetch_github_release", lambda mode: _new_release())
    csrf = _fresh_csrf(client, "/cdc/cau-hinh")

    resp = client.post(
        "/cdc/cau-hinh/cap-nhat/kiem-tra", data={"csrf_token": csrf}, follow_redirects=False,
    )
    assert resp.status_code == 303
    state = web_update.get_public_status()
    assert state["status"] == "available"
    assert state["target_version"] == "9.9.9"
    assert state["sha256"] == "a" * 64

    page = client.get("/cdc/cau-hinh")
    assert "CDC-GiamSatDichBenh-Server-Setup-v9.9.9.exe" in page.text
    assert "Bổ sung cơ chế cập nhật trên trình duyệt." in page.text
    assert any(a["action"] == "check_web_update" for a in core.list_audit_log(db_path=core.DB_PATH))


def test_web_update_refuses_release_without_checksum(client: TestClient, monkeypatch):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    monkeypatch.setattr(update_manager, "fetch_github_release", lambda mode: _new_release(sha256=""))
    csrf = _fresh_csrf(client, "/cdc/cau-hinh")
    client.post("/cdc/cau-hinh/cap-nhat/kiem-tra", data={"csrf_token": csrf})
    assert web_update.get_public_status()["status"] == "blocked"
    assert "SHA-256" in client.get("/cdc/cau-hinh").text


def test_super_admin_can_queue_web_update(client: TestClient, monkeypatch):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    monkeypatch.setattr(update_manager, "fetch_github_release", lambda mode: _new_release())
    monkeypatch.setattr(web_update, "auto_install_supported", lambda _status: True)
    performed = []

    def fake_perform(info, *, actor, db_path):
        performed.append((info.version, actor, str(db_path)))
        web_update._write_status(status="installing", message="Đang cài đặt", progress_percent=96)

    monkeypatch.setattr(web_update, "perform_queued_update", fake_perform)
    csrf = _fresh_csrf(client, "/cdc/cau-hinh")
    resp = client.post(
        "/cdc/cau-hinh/cap-nhat/ap-dung", data={"csrf_token": csrf}, follow_redirects=False,
    )
    assert resp.status_code == 303
    assert performed == [("9.9.9", "sa_admin", str(core.DB_PATH))]
    assert web_update.get_public_status()["status"] == "installing"
    assert any(a["action"] == "queue_web_update" for a in core.list_audit_log(db_path=core.DB_PATH))


def test_web_update_routes_require_super_admin_and_csrf(client: TestClient):
    _login(client, role=core.CDC_ROLE_ADMIN)
    csrf = _fresh_csrf(client, "/cdc/dashboard")
    assert client.post("/cdc/cau-hinh/cap-nhat/kiem-tra", data={"csrf_token": csrf}).status_code == 403
    assert client.post("/cdc/cau-hinh/cap-nhat/ap-dung", data={"csrf_token": csrf}).status_code == 403
    assert client.get("/cdc/cau-hinh/cap-nhat/trang-thai").status_code == 403


def test_web_update_check_requires_csrf(client: TestClient):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    assert client.post("/cdc/cau-hinh/cap-nhat/kiem-tra", data={"csrf_token": "sai"}).status_code == 403


def test_super_admin_can_reset_stuck_update_status(client: TestClient):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    web_update._write_status(status="installing", message="Đang cài...", progress_percent=96, target_version="9.9.9")
    csrf = _fresh_csrf(client, "/cdc/cau-hinh")
    resp = client.post("/cdc/cau-hinh/cap-nhat/dat-lai", data={"csrf_token": csrf}, follow_redirects=False)
    assert resp.status_code == 303
    assert web_update.get_public_status()["status"] == "idle"
    assert any(a["action"] == "web_update_status_reset" for a in core.list_audit_log(db_path=core.DB_PATH))


def test_reset_update_status_requires_super_admin_and_csrf(client: TestClient):
    _login(client, role=core.CDC_ROLE_ADMIN)
    csrf = _fresh_csrf(client, "/cdc/dashboard")
    assert client.post("/cdc/cau-hinh/cap-nhat/dat-lai", data={"csrf_token": csrf}).status_code == 403

    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    assert client.post("/cdc/cau-hinh/cap-nhat/dat-lai", data={"csrf_token": "sai"}).status_code == 403
