"""Kiểm thử luồng xác thực Web App: thiết lập lần đầu, đăng nhập, buộc đổi mật khẩu, khoá tài
khoản, CSRF, đăng xuất — Giai đoạn 2 của nhiệm vụ chuyển sang Web App (xem TASKS.md)."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import core
import deployment_config


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    """Mỗi test dùng CSDL + deployment.json riêng trong thư mục tạm — không đụng dữ liệu thật
    hay lẫn giữa các test chạy song song."""
    monkeypatch.setattr(core, "DATA_DIR", tmp_path / "data")
    core.DATA_DIR.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(core, "DB_PATH", core.DATA_DIR / "test.db")
    monkeypatch.setattr(core, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(deployment_config, "CONFIG_PATH", tmp_path / "deployment.json")

    import webapp.main as webapp_main

    return TestClient(webapp_main.app)


def _csrf_from_cookies(client: TestClient) -> str:
    return client.cookies.get("csrf_token", "")


def test_no_account_redirects_to_setup(client: TestClient):
    resp = client.get("/cdc/login", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/cdc/setup"


def test_setup_then_login_flow(client: TestClient):
    setup_page = client.get("/cdc/setup")
    assert setup_page.status_code == 200
    csrf = _csrf_from_cookies(client)
    assert csrf

    created = client.post(
        "/cdc/setup",
        data={
            "username": "sa_admin", "display_name": "Quản trị chính", "password": "matkhau123",
            "password_confirm": "matkhau123", "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    assert created.headers["location"] == "/cdc/login"

    # Đã có tài khoản -> /cdc/setup không cho tạo thêm, tự chuyển về /cdc/login.
    resp = client.get("/cdc/setup", follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"] == "/cdc/login"

    login_page = client.get("/cdc/login")
    assert login_page.status_code == 200
    csrf2 = _csrf_from_cookies(client)

    logged_in = client.post(
        "/cdc/login", data={"username": "sa_admin", "password": "matkhau123", "csrf_token": csrf2},
        follow_redirects=False,
    )
    assert logged_in.status_code == 303
    # super_admin tạo lúc setup có must_change_password=False -> vào thẳng dashboard.
    assert logged_in.headers["location"] == "/cdc/dashboard"
    assert "cdc_session" in logged_in.cookies

    dashboard = client.get("/cdc/dashboard")
    assert dashboard.status_code == 200
    assert "sa_admin" in dashboard.text or "Quản trị chính" in dashboard.text


def test_forced_password_change_blocks_other_pages(client: TestClient):
    _create_super_admin(client)
    core.create_cdc_account("cdc_moi", "matkhau123", db_path=core.DB_PATH)  # must_change_password mặc định True

    csrf = _csrf_from_cookies(client) or _get_csrf(client, "/cdc/login")
    login = client.post(
        "/cdc/login", data={"username": "cdc_moi", "password": "matkhau123", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert login.headers["location"] == "/cdc/change-password"

    # Cố vào /cdc/dashboard khi chưa đổi mật khẩu -> bị đá về /cdc/change-password.
    dash = client.get("/cdc/dashboard", follow_redirects=False)
    assert dash.status_code == 303 and dash.headers["location"] == "/cdc/change-password"

    change_page = client.get("/cdc/change-password")
    csrf2 = _csrf_from_cookies(client)
    changed = client.post(
        "/cdc/change-password",
        data={
            "current_password": "matkhau123", "new_password": "matkhaumoi123",
            "new_password_confirm": "matkhaumoi123", "csrf_token": csrf2,
        },
        follow_redirects=False,
    )
    assert changed.status_code == 303 and changed.headers["location"] == "/cdc/dashboard"

    # Giờ vào dashboard bình thường được.
    dash2 = client.get("/cdc/dashboard")
    assert dash2.status_code == 200


def test_account_lockout_after_repeated_failures(client: TestClient):
    _create_super_admin(client)
    core.create_cdc_account("cdc_khoa", "matkhau123", must_change_password=False, db_path=core.DB_PATH)

    for _ in range(core.ACCOUNT_LOCKOUT_THRESHOLD):
        csrf = _get_csrf(client, "/cdc/login")
        client.post("/cdc/login", data={"username": "cdc_khoa", "password": "sai", "csrf_token": csrf})

    csrf = _get_csrf(client, "/cdc/login")
    resp = client.post(
        "/cdc/login", data={"username": "cdc_khoa", "password": "matkhau123", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert resp.status_code == 200  # không redirect -> đăng nhập thất bại (đang khoá)
    assert "khoá" in resp.text.lower() or "khoa" in resp.text.lower()


def test_login_rejects_missing_or_wrong_csrf(client: TestClient):
    _create_super_admin(client)
    resp = client.post(
        "/cdc/login", data={"username": "sa_admin", "password": "matkhau123", "csrf_token": "sai-token"},
        follow_redirects=False,
    )
    assert resp.status_code == 200  # ở lại trang login, không redirect thành công
    assert "cdc_session" not in resp.cookies


def test_logout_clears_session(client: TestClient):
    _create_super_admin(client)
    csrf = _get_csrf(client, "/cdc/login")
    client.post("/cdc/login", data={"username": "sa_admin", "password": "matkhau123", "csrf_token": csrf})
    assert client.get("/cdc/dashboard").status_code == 200

    csrf2 = _csrf_from_cookies(client)
    logout = client.post("/cdc/logout", data={"csrf_token": csrf2}, follow_redirects=False)
    assert logout.status_code == 303 and logout.headers["location"] == "/cdc/login"

    after = client.get("/cdc/dashboard", follow_redirects=False)
    assert after.status_code == 303
    assert after.headers["location"].startswith("/cdc/login")


def test_health_endpoint_ok(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


def _get_csrf(client: TestClient, path: str) -> str:
    client.get(path)
    return client.cookies.get("csrf_token", "")


def _create_super_admin(client: TestClient) -> None:
    client.get("/cdc/setup")
    csrf = client.cookies.get("csrf_token", "")
    client.post(
        "/cdc/setup",
        data={
            "username": "sa_admin", "display_name": "Quản trị chính", "password": "matkhau123",
            "password_confirm": "matkhau123", "csrf_token": csrf,
        },
    )
