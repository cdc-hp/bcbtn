"""Kiểm thử router `webapp/routers/ha.py` (máy chủ dự phòng — failover thủ công) và middleware
chặn ghi dữ liệu khi `server_role == "standby"` trong `webapp/main.py`. Xem CLAUDE.md mục "Máy
chủ dự phòng". Theo đúng mẫu fixture của `tests/test_webapp_settings.py`."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backup_manager
import core
import deployment_config
import ha_sync


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

    from webapp.services.rate_limit import ha_peer_limiter, queue_submit_limiter
    queue_submit_limiter._hits.clear()
    ha_peer_limiter._hits.clear()

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


def _set_role(role: str, *, peer_url: str = "", peer_key: str = "") -> None:
    config = deployment_config.load_config()
    config.server_role = role
    if peer_url:
        config.peer_server_url = peer_url
    if peer_key:
        config.peer_shared_key = peer_key
    deployment_config.save_config(config)


# --- Middleware chặn ghi khi standby --------------------------------------------------------

def test_standby_blocks_queue_submit_xa(client: TestClient):
    _set_role("standby")
    resp = client.post("/queue/submit-xa", json={"commune": "x", "week": "2026-W01"})
    assert resp.status_code == 409
    assert resp.json()["ok"] is False


def test_standby_blocks_generic_admin_write(client: TestClient):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    _set_role("standby")
    csrf = _fresh_csrf(client, "/cdc/dashboard")
    resp = client.post("/cdc/dashboard/dong-bo-may-chu-phu", data={"csrf_token": csrf})
    assert resp.status_code == 409
    assert "dự phòng" in resp.text.lower()


def test_standby_still_allows_cau_hinh_and_vai_tro(client: TestClient):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    _set_role("standby")
    csrf = _fresh_csrf(client, "/cdc/cau-hinh")
    resp = client.post("/cdc/vai-tro-may-chu/thang-cap", data={"csrf_token": csrf}, follow_redirects=False)
    assert resp.status_code == 303  # không bị middleware chặn (409)


def test_primary_does_not_block_writes(client: TestClient):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    csrf = _fresh_csrf(client, "/cdc/dashboard")
    resp = client.post("/cdc/dashboard/dong-bo-may-chu-phu", data={"csrf_token": csrf}, follow_redirects=False)
    assert resp.status_code != 409


# --- /cdc/vai-tro-may-chu/* (super-admin) --------------------------------------------------

def test_promote_sets_primary_and_logs_audit(client: TestClient):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    _set_role("standby")
    csrf = _fresh_csrf(client, "/cdc/cau-hinh")
    resp = client.post("/cdc/vai-tro-may-chu/thang-cap", data={"csrf_token": csrf}, follow_redirects=False)
    assert resp.status_code == 303
    assert deployment_config.load_config().server_role == "primary"
    actions = core.list_audit_log(db_path=core.DB_PATH)
    assert any(a["action"] == "promote_to_primary" for a in actions)


def test_promote_pulls_final_catch_up_before_switching_role(client: TestClient, monkeypatch):
    """Thăng cấp phải kéo bù 1 lần cuối TRƯỚC khi đổi vai trò (còn là dự phòng lúc gọi), theo
    đúng yêu cầu "kéo dữ liệu từ máy dự phòng để bổ sung dữ liệu ... rồi chuyển máy chính"."""
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    _set_role("standby", peer_url="http://192.168.1.99:8765", peer_key="khoa")
    calls: list[str] = []

    def _fake_pull(db_path=None):
        calls.append(deployment_config.load_config().server_role)
        return {"restored_from": "fake.db"}

    monkeypatch.setattr(ha_sync, "run_standby_pull_once", _fake_pull)
    monkeypatch.setattr(ha_sync, "notify_peer_demote", lambda url, key: True)
    csrf = _fresh_csrf(client, "/cdc/cau-hinh")
    client.post("/cdc/vai-tro-may-chu/thang-cap", data={"csrf_token": csrf}, follow_redirects=False)

    assert calls == ["standby"]  # kéo bù trong khi CÒN là dự phòng, trước khi đổi vai trò
    actions = core.list_audit_log(db_path=core.DB_PATH)
    promote_action = next(a for a in actions if a["action"] == "promote_to_primary")
    assert "catch_up=ok" in promote_action["detail"]


def test_promote_warns_when_peer_notify_fails(client: TestClient, monkeypatch):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    _set_role("standby", peer_url="http://192.168.1.99:8765", peer_key="khoa")
    monkeypatch.setattr(ha_sync, "run_standby_pull_once", lambda db_path=None: {"skipped": True, "reason": "test"})
    monkeypatch.setattr(ha_sync, "notify_peer_demote", lambda url, key: False)
    csrf = _fresh_csrf(client, "/cdc/cau-hinh")
    resp = client.post("/cdc/vai-tro-may-chu/thang-cap", data={"csrf_token": csrf}, follow_redirects=False)
    assert "err=" in resp.headers["location"]


def test_demote_self_sets_standby(client: TestClient):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    csrf = _fresh_csrf(client, "/cdc/cau-hinh")
    resp = client.post("/cdc/vai-tro-may-chu/xuong-cap", data={"csrf_token": csrf}, follow_redirects=False)
    assert resp.status_code == 303
    assert deployment_config.load_config().server_role == "standby"


def test_role_routes_require_super_admin(client: TestClient):
    _login(client, role=core.CDC_ROLE_ADMIN)
    csrf = _fresh_csrf(client, "/cdc/dashboard")
    assert client.post("/cdc/vai-tro-may-chu/thang-cap", data={"csrf_token": csrf}).status_code == 403
    assert client.post("/cdc/vai-tro-may-chu/xuong-cap", data={"csrf_token": csrf}).status_code == 403
    assert client.get("/cdc/vai-tro-may-chu/trang-thai").status_code == 403


def test_role_routes_require_csrf(client: TestClient):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    resp = client.post("/cdc/vai-tro-may-chu/thang-cap", data={"csrf_token": "sai"})
    assert resp.status_code == 403


# --- /noi-bo/ha/* (máy-tới-máy) -------------------------------------------------------------

def test_demote_endpoint_requires_correct_key(client: TestClient):
    _set_role("primary", peer_key="khoa-dung")
    resp = client.post("/noi-bo/ha/demote", headers={"X-CDC-Peer-Key": "khoa-sai"})
    assert resp.status_code == 401
    assert deployment_config.load_config().server_role == "primary"


def test_demote_endpoint_sets_standby_with_correct_key(client: TestClient):
    _set_role("primary", peer_key="khoa-dung")
    resp = client.post("/noi-bo/ha/demote", headers={"X-CDC-Peer-Key": "khoa-dung"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert deployment_config.load_config().server_role == "standby"


def test_snapshot_requires_correct_key(client: TestClient):
    _set_role("primary", peer_key="khoa-dung")
    resp = client.get("/noi-bo/ha/snapshot", headers={"X-CDC-Peer-Key": "khoa-sai"})
    assert resp.status_code == 401


def test_snapshot_refuses_when_not_primary(client: TestClient):
    _set_role("standby", peer_key="khoa-dung")
    resp = client.get("/noi-bo/ha/snapshot", headers={"X-CDC-Peer-Key": "khoa-dung"})
    assert resp.status_code == 409


def test_snapshot_returns_file_when_primary(client: TestClient):
    _set_role("primary", peer_key="khoa-dung")
    core.init_db(core.DB_PATH)
    resp = client.get("/noi-bo/ha/snapshot", headers={"X-CDC-Peer-Key": "khoa-dung"})
    assert resp.status_code == 200
    assert resp.content[:16] == b"SQLite format 3\x00"


def test_role_status_requires_correct_key(client: TestClient):
    _set_role("primary", peer_key="khoa-dung")
    resp = client.get("/noi-bo/ha/vai-tro", headers={"X-CDC-Peer-Key": "khoa-sai"})
    assert resp.status_code == 401


def test_role_status_reports_current_role(client: TestClient):
    _set_role("standby", peer_key="khoa-dung")
    resp = client.get("/noi-bo/ha/vai-tro", headers={"X-CDC-Peer-Key": "khoa-dung"})
    assert resp.status_code == 200
    assert resp.json()["server_role"] == "standby"


def test_request_sync_endpoint_requires_correct_key(client: TestClient):
    _set_role("standby", peer_key="khoa-dung")
    resp = client.post("/noi-bo/ha/yeu-cau-dong-bo", headers={"X-CDC-Peer-Key": "khoa-sai"})
    assert resp.status_code == 401


def test_request_sync_endpoint_refuses_when_not_standby(client: TestClient):
    _set_role("primary", peer_key="khoa-dung")
    resp = client.post("/noi-bo/ha/yeu-cau-dong-bo", headers={"X-CDC-Peer-Key": "khoa-dung"})
    assert resp.status_code == 409


def test_request_sync_endpoint_triggers_pull_when_standby(client: TestClient, monkeypatch):
    _set_role("standby", peer_key="khoa-dung", peer_url="http://192.168.1.99:8765")
    monkeypatch.setattr(ha_sync, "run_standby_pull_once", lambda db_path=None: {"restored_from": "fake.db"})
    resp = client.post("/noi-bo/ha/yeu-cau-dong-bo", headers={"X-CDC-Peer-Key": "khoa-dung"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "result": {"restored_from": "fake.db"}}


def test_request_sync_endpoint_surfaces_pull_error(client: TestClient, monkeypatch):
    _set_role("standby", peer_key="khoa-dung", peer_url="http://192.168.1.99:8765")
    monkeypatch.setattr(ha_sync, "run_standby_pull_once", lambda db_path=None: {"error": "khong ket noi duoc"})
    resp = client.post("/noi-bo/ha/yeu-cau-dong-bo", headers={"X-CDC-Peer-Key": "khoa-dung"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is False


# --- /cdc/vai-tro-may-chu/yeu-cau-may-kia-dong-bo (primary chủ động nhờ standby đồng bộ) -----

def test_request_peer_sync_requires_super_admin(client: TestClient):
    _login(client, role=core.CDC_ROLE_ADMIN)
    csrf = _fresh_csrf(client, "/cdc/dashboard")
    resp = client.post("/cdc/vai-tro-may-chu/yeu-cau-may-kia-dong-bo", data={"csrf_token": csrf})
    assert resp.status_code == 403


def test_request_peer_sync_requires_peer_configured(client: TestClient):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    csrf = _fresh_csrf(client, "/cdc/cau-hinh")
    resp = client.post("/cdc/vai-tro-may-chu/yeu-cau-may-kia-dong-bo", data={"csrf_token": csrf}, follow_redirects=False)
    assert "err=" in resp.headers["location"]


def test_request_peer_sync_success_redirects_with_message(client: TestClient, monkeypatch):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    _set_role("primary", peer_url="http://192.168.1.99:8765", peer_key="khoa")
    monkeypatch.setattr(ha_sync, "request_peer_sync_now", lambda url, key: {"ok": True, "result": {"restored_from": "fake.db"}})
    csrf = _fresh_csrf(client, "/cdc/cau-hinh")
    resp = client.post("/cdc/vai-tro-may-chu/yeu-cau-may-kia-dong-bo", data={"csrf_token": csrf}, follow_redirects=False)
    assert "msg=" in resp.headers["location"]
    actions = core.list_audit_log(db_path=core.DB_PATH)
    assert any(a["action"] == "ha_request_peer_sync" for a in actions)


def test_request_peer_sync_failure_redirects_with_error(client: TestClient, monkeypatch):
    _login(client, role=core.CDC_ROLE_SUPER_ADMIN)
    _set_role("primary", peer_url="http://192.168.1.99:8765", peer_key="khoa")
    monkeypatch.setattr(ha_sync, "request_peer_sync_now", lambda url, key: {"ok": False, "error": "HTTP 403"})
    csrf = _fresh_csrf(client, "/cdc/cau-hinh")
    resp = client.post("/cdc/vai-tro-may-chu/yeu-cau-may-kia-dong-bo", data={"csrf_token": csrf}, follow_redirects=False)
    assert "err=" in resp.headers["location"]


def test_noi_bo_ha_endpoints_are_rate_limited(client: TestClient):
    """`/noi-bo/ha/*` công khai ra Internet (mỗi máy 1 tên miền Cloudflare Tunnel riêng, xem
    CLAUDE.md mục "Máy chủ dự phòng") nên cần giới hạn tần suất chống dò `peer_shared_key`."""
    _set_role("primary", peer_key="khoa-dung")
    for _ in range(20):
        resp = client.get("/noi-bo/ha/vai-tro", headers={"X-CDC-Peer-Key": "khoa-sai"})
        assert resp.status_code == 401
    resp = client.get("/noi-bo/ha/vai-tro", headers={"X-CDC-Peer-Key": "khoa-sai"})
    assert resp.status_code == 429
