"""Kiểm thử `/cdc/lich-su-nhap` — xem lịch sử nhập + xóa nguyên một lần nhập (xem TASKS.md)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

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


def _seed_case_file(tmp_path: Path, name: str, rows: list[dict]) -> Path:
    wb = Workbook(); ws = wb.active; ws.title = "Disease Cases"
    ws.append([label for label, _ in core.CASE_FIELDS])
    for row in rows:
        full = {key: "" for _, key in core.CASE_FIELDS}
        full.update(row)
        ws.append([full.get(key, "") for _, key in core.CASE_FIELDS])
    path = tmp_path / name
    wb.save(path)
    return path


def test_list_shows_batches(client: TestClient, tmp_path: Path):
    _login(client)
    core.import_excel(_seed_case_file(tmp_path, "a.xlsx", [{"full_name": "Nguyen Van A"}]), core.DB_PATH)
    resp = client.get("/cdc/lich-su-nhap")
    assert resp.status_code == 200 and "a.xlsx" in resp.text


def test_viewer_forbidden(client: TestClient):
    _login(client, role=core.CDC_ROLE_VIEWER)
    resp = client.get("/cdc/lich-su-nhap")
    assert resp.status_code == 403


def test_data_operator_can_view_but_not_delete_button(client: TestClient, tmp_path: Path):
    _login(client, role=core.CDC_ROLE_DATA_OPERATOR)
    core.import_excel(_seed_case_file(tmp_path, "b.xlsx", [{"full_name": "Nguyen Van B"}]), core.DB_PATH)
    resp = client.get("/cdc/lich-su-nhap")
    assert resp.status_code == 200
    assert "Xóa lần nhập này" not in resp.text


def test_delete_batch_removes_only_that_batch(client: TestClient, tmp_path: Path):
    _login(client)
    core.import_excel(_seed_case_file(tmp_path, "first.xlsx", [
        {"full_name": "Nguyen Van A"}, {"full_name": "Nguyen Van B"},
    ]), core.DB_PATH)
    time.sleep(1.1)  # đảm bảo imported_at (độ chính xác giây) khác lần nhập thứ 2
    core.import_excel(_seed_case_file(tmp_path, "second.xlsx", [{"full_name": "Tran Van C"}]), core.DB_PATH)

    batches = core.list_import_batches(db_path=core.DB_PATH)
    first_batch = next(b for b in batches if b["file_name"] == "first.xlsx")
    second_batch = next(b for b in batches if b["file_name"] == "second.xlsx")

    csrf = _fresh_csrf(client, "/cdc/lich-su-nhap")
    resp = client.post(f"/cdc/lich-su-nhap/{first_batch['id']}/xoa", data={"csrf_token": csrf}, follow_redirects=False)
    assert resp.status_code == 303
    assert "msg=" in resp.headers["location"]

    remaining_cases = core.query_records("case", db_path=core.DB_PATH)[0]
    assert len(remaining_cases) == 1
    assert remaining_cases[0]["full_name"] == "Tran Van C"

    remaining_batches = core.list_import_batches(db_path=core.DB_PATH)
    assert first_batch["id"] not in {b["id"] for b in remaining_batches}
    assert second_batch["id"] in {b["id"] for b in remaining_batches}


def test_delete_batch_removes_quality_issues(client: TestClient, tmp_path: Path):
    _login(client)
    # Chỉ đặt full_name -> thiếu case_code/main_diagnosis/onset_date, chắc chắn sinh cảnh báo
    # chất lượng dữ liệu gắn với bản ghi này (xem core._quality_checks).
    core.import_excel(_seed_case_file(tmp_path, "issues.xlsx", [
        {"full_name": "Nguyen Van A"},
    ]), core.DB_PATH)
    batch = core.list_import_batches(db_path=core.DB_PATH)[0]

    csrf = _fresh_csrf(client, "/cdc/lich-su-nhap")
    client.post(f"/cdc/lich-su-nhap/{batch['id']}/xoa", data={"csrf_token": csrf})

    issues = core.list_quality_issues(entity_type="case", db_path=core.DB_PATH)
    assert issues == []


def test_delete_nonexistent_batch_shows_error(client: TestClient):
    _login(client)
    csrf = _fresh_csrf(client, "/cdc/lich-su-nhap")
    resp = client.post("/cdc/lich-su-nhap/99999/xoa", data={"csrf_token": csrf}, follow_redirects=False)
    assert resp.status_code == 303 and "err=" in resp.headers["location"]


def test_delete_requires_csrf(client: TestClient, tmp_path: Path):
    _login(client)
    core.import_excel(_seed_case_file(tmp_path, "c.xlsx", [{"full_name": "Nguyen Van D"}]), core.DB_PATH)
    batch = core.list_import_batches(db_path=core.DB_PATH)[0]
    resp = client.post(f"/cdc/lich-su-nhap/{batch['id']}/xoa", data={"csrf_token": "sai"})
    assert resp.status_code == 403


def test_delete_requires_admin_role(client: TestClient, tmp_path: Path):
    _login(client, role=core.CDC_ROLE_DATA_OPERATOR)
    core.import_excel(_seed_case_file(tmp_path, "d.xlsx", [{"full_name": "Nguyen Van E"}]), core.DB_PATH)
    batch = core.list_import_batches(db_path=core.DB_PATH)[0]
    csrf = _fresh_csrf(client, "/cdc/lich-su-nhap")
    resp = client.post(f"/cdc/lich-su-nhap/{batch['id']}/xoa", data={"csrf_token": csrf})
    assert resp.status_code == 403
