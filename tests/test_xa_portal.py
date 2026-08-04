"""Kiểm thử cổng đăng nhập tài khoản xã (`/xa/*`) — xem CLAUDE.md mục "Tài khoản xã". Trọng tâm
là kiểm thử BẢO MẬT: xã A tuyệt đối không được thấy dữ liệu xã B, kể cả khi cố truyền tham số qua
query string hoặc đoán ID bản ghi trên URL."""

from __future__ import annotations

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


def _seed_cases(tmp_path: Path, rows: list[dict]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Disease Cases"
    ws.append([label for label, _ in core.CASE_FIELDS])
    for row in rows:
        full = {key: "" for _, key in core.CASE_FIELDS}
        full.update(row)
        ws.append([full.get(key, "") for _, key in core.CASE_FIELDS])
    path = tmp_path / "seed_cases.xlsx"
    wb.save(path)
    core.import_excel(path, core.DB_PATH)


def _seed_outbreak(**overrides) -> int:
    # `admin_area` KHÔNG phải field người dùng đặt được trực tiếp — core.save_outbreak() luôn tự
    # tính lại bằng core.extract_admin_area(location) (xem core.py::_normalize_payload), nên phải
    # đặt `location` chứa đúng chuỗi "Xã .../Phường ..." để suy ra đúng admin_area mong muốn.
    data = {
        "disease": "Sốt xuất huyết", "location": COMMUNE_A, "first_onset_date": "2026-07-01",
        "status": "Đang hoạt động", "case_count": 5, "death_count": 0, "reporting_unit": "TYT",
    }
    data.update(overrides)
    return core.save_outbreak(data, db_path=core.DB_PATH)


def _create_account(commune: str, username: str, password: str = "matkhau123") -> dict:
    return core.create_commune_account(commune, username, password, db_path=core.DB_PATH)


def _login_xa(client: TestClient, username: str, password: str = "matkhau123") -> None:
    client.get("/xa/dang-nhap")
    csrf = client.cookies.get("csrf_token", "")
    client.post("/xa/dang-nhap", data={"csrf_token": csrf, "username": username, "password": password})


# --- Đăng nhập / đăng xuất -------------------------------------------------------------------

def test_login_success(client: TestClient):
    _create_account(COMMUNE_A, "xa_a")
    _login_xa(client, "xa_a")
    resp = client.get("/xa/ca-benh")
    assert resp.status_code == 200


def test_login_wrong_password(client: TestClient):
    _create_account(COMMUNE_A, "xa_a")
    client.get("/xa/dang-nhap")
    csrf = client.cookies.get("csrf_token", "")
    resp = client.post("/xa/dang-nhap", data={"csrf_token": csrf, "username": "xa_a", "password": "sai"})
    assert resp.status_code == 200
    assert "Sai tên đăng nhập" in resp.text


def test_locked_account_cannot_login(client: TestClient):
    result = _create_account(COMMUNE_A, "xa_a")
    core.set_commune_account_active(result["id"], False, db_path=core.DB_PATH)
    client.get("/xa/dang-nhap")
    csrf = client.cookies.get("csrf_token", "")
    resp = client.post("/xa/dang-nhap", data={"csrf_token": csrf, "username": "xa_a", "password": "matkhau123"})
    assert "Sai tên đăng nhập" in resp.text


def test_unauthenticated_redirects_to_login(client: TestClient):
    resp = client.get("/xa/ca-benh", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/xa/dang-nhap")


def test_logout_clears_session(client: TestClient):
    _create_account(COMMUNE_A, "xa_a")
    _login_xa(client, "xa_a")
    csrf = client.cookies.get("csrf_token", "")
    client.post("/xa/dang-xuat", data={"csrf_token": csrf})
    resp = client.get("/xa/ca-benh", follow_redirects=False)
    assert resp.status_code == 303


# --- Cách ly dữ liệu chéo xã (bảo mật cốt lõi) -----------------------------------------------

def test_case_list_only_shows_own_commune(client: TestClient, tmp_path: Path):
    _seed_cases(tmp_path, [
        {"case_code": "CA-A", "full_name": "Nguyễn Văn A", "commune": COMMUNE_A},
        {"case_code": "CA-B", "full_name": "Trần Thị B", "commune": COMMUNE_B},
    ])
    _create_account(COMMUNE_A, "xa_a")
    _login_xa(client, "xa_a")

    resp = client.get("/xa/ca-benh")
    assert resp.status_code == 200
    assert "CA-A" in resp.text
    assert "CA-B" not in resp.text
    assert "Trần Thị B" not in resp.text


def test_case_list_and_detail_show_dates_as_dd_mm_yyyy(client: TestClient, tmp_path: Path):
    _seed_cases(tmp_path, [
        {"case_code": "CA-A", "full_name": "Nguyễn Văn A", "commune": COMMUNE_A, "onset_date": "10/07/2026"},
    ])
    _create_account(COMMUNE_A, "xa_a")
    _login_xa(client, "xa_a")

    list_resp = client.get("/xa/ca-benh")
    assert "10/07/2026" in list_resp.text
    assert "2026-07-10" not in list_resp.text

    record = core.query_records("case", db_path=core.DB_PATH)[0][0]
    detail_resp = client.get(f"/xa/ca-benh/{record['id']}")
    assert "10/07/2026" in detail_resp.text
    assert "2026-07-10" not in detail_resp.text


def test_case_list_ignores_admin_area_query_param_override(client: TestClient, tmp_path: Path):
    """Cố truyền ?admin_area=<xã khác> qua query string phải KHÔNG có tác dụng gì — router
    xa_view.py không nhận admin_area từ query string, luôn tự gán từ phiên đăng nhập."""
    _seed_cases(tmp_path, [
        {"case_code": "CA-A", "full_name": "Nguyễn Văn A", "commune": COMMUNE_A},
        {"case_code": "CA-B", "full_name": "Trần Thị B", "commune": COMMUNE_B},
    ])
    _create_account(COMMUNE_A, "xa_a")
    _login_xa(client, "xa_a")

    resp = client.get(f"/xa/ca-benh?admin_area={COMMUNE_B}")
    assert "CA-B" not in resp.text
    assert "Trần Thị B" not in resp.text


def test_outbreak_list_only_shows_own_commune(client: TestClient):
    _seed_outbreak(disease="Sởi", location=COMMUNE_A)
    _seed_outbreak(disease="Cúm B", location=COMMUNE_B)
    _create_account(COMMUNE_A, "xa_a")
    _login_xa(client, "xa_a")

    resp = client.get("/xa/o-dich")
    assert "Sởi" in resp.text
    assert "Cúm B" not in resp.text


def test_case_detail_of_other_commune_not_accessible(client: TestClient, tmp_path: Path):
    """Đoán số ID bản ghi thuộc xã khác trên URL phải không xem được (chặn IDOR)."""
    _seed_cases(tmp_path, [
        {"case_code": "CA-B", "full_name": "Trần Thị B", "commune": COMMUNE_B},
    ])
    rows, _ = core.query_records("case", db_path=core.DB_PATH)
    other_case_id = rows[0]["id"]

    _create_account(COMMUNE_A, "xa_a")
    _login_xa(client, "xa_a")
    resp = client.get(f"/xa/ca-benh/{other_case_id}")
    assert resp.status_code == 403
    assert "Trần Thị B" not in resp.text


def test_outbreak_detail_of_own_commune_accessible(client: TestClient):
    outbreak_id = _seed_outbreak(disease="Sởi", location=COMMUNE_A)
    _create_account(COMMUNE_A, "xa_a")
    _login_xa(client, "xa_a")
    resp = client.get(f"/xa/o-dich/{outbreak_id}")
    assert resp.status_code == 200
    assert "Sởi" in resp.text


def test_two_different_communes_each_see_only_their_own(client: TestClient, tmp_path: Path):
    _seed_cases(tmp_path, [
        {"case_code": "CA-A", "full_name": "Nguyễn Văn A", "commune": COMMUNE_A},
        {"case_code": "CA-B", "full_name": "Trần Thị B", "commune": COMMUNE_B},
    ])
    _create_account(COMMUNE_A, "xa_a")
    _create_account(COMMUNE_B, "xa_b")

    client_a = TestClient(client.app)
    client_a.get("/xa/dang-nhap")
    csrf_a = client_a.cookies.get("csrf_token", "")
    client_a.post("/xa/dang-nhap", data={"csrf_token": csrf_a, "username": "xa_a", "password": "matkhau123"})
    resp_a = client_a.get("/xa/ca-benh")
    assert "CA-A" in resp_a.text and "CA-B" not in resp_a.text

    client_b = TestClient(client.app)
    client_b.get("/xa/dang-nhap")
    csrf_b = client_b.cookies.get("csrf_token", "")
    client_b.post("/xa/dang-nhap", data={"csrf_token": csrf_b, "username": "xa_b", "password": "matkhau123"})
    resp_b = client_b.get("/xa/ca-benh")
    assert "CA-B" in resp_b.text and "CA-A" not in resp_b.text
