"""Kiểm thử `/cdc/tai-khoan-xa` (quản lý tài khoản xã, chỉ super_admin) và
`core.import_commune_accounts` (nhập hàng loạt qua Excel) — xem CLAUDE.md mục "Tài khoản xã"."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

import core
import deployment_config

COMMUNE_A = "Xã An Hưng"
COMMUNE_B = "Xã Kiến Thụy"


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


def _login_super_admin(client: TestClient) -> None:
    client.get("/cdc/setup")
    csrf = client.cookies.get("csrf_token", "")
    client.post("/cdc/setup", data={
        "username": "sa_admin", "display_name": "Super", "password": "matkhau123",
        "password_confirm": "matkhau123", "csrf_token": csrf,
    })
    csrf2 = _fresh_csrf(client, "/cdc/login")
    client.post("/cdc/login", data={"username": "sa_admin", "password": "matkhau123", "csrf_token": csrf2})


def _login_admin(client: TestClient) -> None:
    client.get("/cdc/setup")
    csrf = client.cookies.get("csrf_token", "")
    client.post("/cdc/setup", data={
        "username": "sa_admin", "display_name": "Super", "password": "matkhau123",
        "password_confirm": "matkhau123", "csrf_token": csrf,
    })
    core.create_cdc_account("admin_user", "matkhau123", role=core.CDC_ROLE_ADMIN, must_change_password=False, db_path=core.DB_PATH)
    csrf2 = _fresh_csrf(client, "/cdc/login")
    client.post("/cdc/login", data={"username": "admin_user", "password": "matkhau123", "csrf_token": csrf2})


def _excel_bytes(rows: list[list[str]], header: list[str] | None = None) -> bytes:
    header = header or ["Xã/Phường", "Tên đăng nhập", "Mật khẩu", "Tên hiển thị"]
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_requires_super_admin(client: TestClient):
    _login_admin(client)
    resp = client.get("/cdc/tai-khoan-xa")
    assert resp.status_code == 403


def test_create_account(client: TestClient):
    _login_super_admin(client)
    csrf = _fresh_csrf(client, "/cdc/tai-khoan-xa")
    resp = client.post("/cdc/tai-khoan-xa/tao", data={
        "csrf_token": csrf, "commune": COMMUNE_A, "username": "xa_anhung",
        "display_name": "", "password": "matkhau123",
    }, follow_redirects=False)
    assert resp.status_code == 303
    assert "msg=" in resp.headers["location"]
    accounts = core.list_commune_accounts(db_path=core.DB_PATH)
    created = next(a for a in accounts if a["username"] == "xa_anhung")
    assert created["commune"] == COMMUNE_A


def test_create_account_rejects_unofficial_commune(client: TestClient):
    _login_super_admin(client)
    csrf = _fresh_csrf(client, "/cdc/tai-khoan-xa")
    resp = client.post("/cdc/tai-khoan-xa/tao", data={
        "csrf_token": csrf, "commune": "Xã Không Tồn Tại", "username": "xa_sai",
        "password": "matkhau123",
    }, follow_redirects=False)
    assert "err=" in resp.headers["location"]
    assert not core.list_commune_accounts(db_path=core.DB_PATH)


def test_create_account_rejects_short_password(client: TestClient):
    _login_super_admin(client)
    csrf = _fresh_csrf(client, "/cdc/tai-khoan-xa")
    resp = client.post("/cdc/tai-khoan-xa/tao", data={
        "csrf_token": csrf, "commune": COMMUNE_A, "username": "xa_ngan", "password": "123",
    }, follow_redirects=False)
    assert "err=" in resp.headers["location"]


def test_actions_require_csrf(client: TestClient):
    _login_super_admin(client)
    resp = client.post("/cdc/tai-khoan-xa/tao", data={
        "csrf_token": "sai", "commune": COMMUNE_A, "username": "x", "password": "matkhau123",
    })
    assert resp.status_code == 403


def test_toggle_active_and_reset_password(client: TestClient):
    _login_super_admin(client)
    result = core.create_commune_account(COMMUNE_A, "xa_toggle", "matkhau123", db_path=core.DB_PATH)
    csrf = _fresh_csrf(client, "/cdc/tai-khoan-xa")
    client.post(f"/cdc/tai-khoan-xa/{result['id']}/kich-hoat", data={"csrf_token": csrf, "active": "0"})
    accounts = core.list_commune_accounts(db_path=core.DB_PATH)
    assert next(a for a in accounts if a["id"] == result["id"])["active"] == 0

    resp = client.post(f"/cdc/tai-khoan-xa/{result['id']}/dat-lai-mat-khau", data={
        "csrf_token": csrf, "new_password": "matkhaumoi99",
    }, follow_redirects=False)
    assert resp.status_code == 303


# --- Nhập hàng loạt qua Excel ---------------------------------------------------------------

def test_import_excel_creates_accounts(client: TestClient):
    _login_super_admin(client)
    data = _excel_bytes([
        [COMMUNE_A, "xa_a", "matkhau123", "Xã A"],
        [COMMUNE_B, "xa_b", "matkhau456", ""],
    ])
    csrf = _fresh_csrf(client, "/cdc/tai-khoan-xa")
    resp = client.post(
        "/cdc/tai-khoan-xa/nhap-excel",
        data={"csrf_token": csrf},
        files={"file": ("xa.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "msg=" in resp.headers["location"]
    accounts = {a["commune"]: a for a in core.list_commune_accounts(db_path=core.DB_PATH)}
    assert COMMUNE_A in accounts and COMMUNE_B in accounts


def test_import_excel_reports_unofficial_commune_row(client: TestClient):
    _login_super_admin(client)
    data = _excel_bytes([
        [COMMUNE_A, "xa_a", "matkhau123", ""],
        ["Xã Bịa Đặt", "xa_bia", "matkhau123", ""],
    ])
    csrf = _fresh_csrf(client, "/cdc/tai-khoan-xa")
    resp = client.post(
        "/cdc/tai-khoan-xa/nhap-excel", data={"csrf_token": csrf},
        files={"file": ("xa.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        follow_redirects=False,
    )
    assert "msg=" in resp.headers["location"]  # 1 dòng thành công vẫn coi là msg (có kèm lỗi)
    accounts = core.list_commune_accounts(db_path=core.DB_PATH)
    assert len(accounts) == 1
    assert accounts[0]["commune"] == COMMUNE_A


def test_import_excel_missing_columns_rejected(client: TestClient):
    _login_super_admin(client)
    data = _excel_bytes([[COMMUNE_A, "xa_a"]], header=["Xã", "Tên đăng nhập"])
    csrf = _fresh_csrf(client, "/cdc/tai-khoan-xa")
    resp = client.post(
        "/cdc/tai-khoan-xa/nhap-excel", data={"csrf_token": csrf},
        files={"file": ("xa.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        follow_redirects=False,
    )
    assert "err=" in resp.headers["location"]
    assert not core.list_commune_accounts(db_path=core.DB_PATH)


def test_import_excel_duplicate_commune_row_reported_as_error(client: TestClient):
    _login_super_admin(client)
    data = _excel_bytes([
        [COMMUNE_A, "xa_a1", "matkhau123", ""],
        [COMMUNE_A, "xa_a2", "matkhau123", ""],
    ])
    csrf = _fresh_csrf(client, "/cdc/tai-khoan-xa")
    resp = client.post(
        "/cdc/tai-khoan-xa/nhap-excel", data={"csrf_token": csrf},
        files={"file": ("xa.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        follow_redirects=False,
    )
    assert "msg=" in resp.headers["location"]
    accounts = core.list_commune_accounts(db_path=core.DB_PATH)
    assert len(accounts) == 1


def test_import_commune_accounts_function_directly(tmp_path: Path):
    """Kiểm thử trực tiếp core.import_commune_accounts (không qua HTTP) — bao quát dòng trống
    cuối file bị bỏ qua đúng cách."""
    monkeypatch_db = tmp_path / "direct.db"
    core.init_db(monkeypatch_db)
    data = _excel_bytes([
        [COMMUNE_A, "xa_a", "matkhau123", ""],
        ["", "", "", ""],
        ["", "", "", ""],
    ])
    summary = core.import_commune_accounts(BytesIO(data), db_path=monkeypatch_db)
    assert summary.rows_read == 1
    assert summary.created == 1
    assert not summary.errors
