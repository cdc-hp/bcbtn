"""Kiểm thử Giai đoạn 5: /cdc/loc-trung (quét, duyệt & hợp nhất, thùng rác/lịch sử, tiêu chí) —
xem TASKS.md."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

import core
import deployment_config
import duplicate_config


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(core, "DATA_DIR", tmp_path / "data")
    core.DATA_DIR.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(core, "DB_PATH", core.DATA_DIR / "test.db")
    monkeypatch.setattr(core, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(core, "QUEUE_DIR", tmp_path / "queue")
    monkeypatch.setattr(deployment_config, "CONFIG_PATH", tmp_path / "deployment.json")
    monkeypatch.setattr(duplicate_config, "CONFIG_PATH", tmp_path / "duplicate_rules.json")
    monkeypatch.setattr(duplicate_config, "CRITERIA_CONFIG_PATH", tmp_path / "case_duplicate_criteria.json")

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


def _seed_dup_cases(tmp_path: Path) -> None:
    wb = Workbook(); ws = wb.active; ws.title = "Disease Cases"
    ws.append([label for label, _ in core.CASE_FIELDS])
    rows = [
        {"case_code": "CA-DUP", "full_name": "Nguyễn Văn A", "commune": "Xã A", "phone": "0900000001"},
        {"case_code": "CA-DUP", "full_name": "Nguyễn Văn Á", "commune": "Xã A", "phone": "0900000002"},
        {"case_code": "CA-SOLO", "full_name": "Trần Thị B", "commune": "Xã B", "phone": "0900000003"},
    ]
    for row in rows:
        full = {key: "" for _, key in core.CASE_FIELDS}
        full.update(row)
        ws.append([full.get(key, "") for _, key in core.CASE_FIELDS])
    path = tmp_path / "seed_dup_cases.xlsx"
    wb.save(path)
    core.import_excel(path, core.DB_PATH)


def _dup_case_ids() -> list[int]:
    rows, _ = core.query_records("case", db_path=core.DB_PATH)
    return sorted(r["id"] for r in rows if r["case_code"] == "CA-DUP")


# ---------- Quét ----------

def test_scan_requires_login(client: TestClient):
    resp = client.get("/cdc/loc-trung", follow_redirects=False)
    assert resp.status_code == 303


def test_scan_finds_duplicate_case_group(client: TestClient, tmp_path: Path):
    _login(client)
    _seed_dup_cases(tmp_path)
    resp = client.get("/cdc/loc-trung", params={"entity": "case"})
    assert resp.status_code == 200
    assert "CA-DUP" in resp.text
    assert "Duyệt" in resp.text


def test_scan_outbreak_with_min_score(client: TestClient):
    _login(client)
    core.save_outbreak({"disease": "Sởi", "location": "Thôn 1", "case_count": 1}, db_path=core.DB_PATH)
    core.save_outbreak({"disease": "Sởi", "location": "Thôn 1", "case_count": 2}, db_path=core.DB_PATH)
    resp = client.get("/cdc/loc-trung", params={"entity": "outbreak", "min_score": 40})
    assert resp.status_code == 200
    assert "Sởi" in resp.text or "nhóm" in resp.text.lower()


def test_viewer_can_scan_but_no_merge_button(client: TestClient, tmp_path: Path):
    _login(client, role=core.CDC_ROLE_VIEWER)
    _seed_dup_cases(tmp_path)
    resp = client.get("/cdc/loc-trung", params={"entity": "case"})
    assert resp.status_code == 200
    assert "Duyệt &amp; hợp nhất" not in resp.text


# ---------- Duyệt & hợp nhất ----------

def test_review_page_shows_group_records(client: TestClient, tmp_path: Path):
    _login(client)
    _seed_dup_cases(tmp_path)
    ids = _dup_case_ids()
    resp = client.get("/cdc/loc-trung/xem", params={"entity": "case", "ids": ",".join(map(str, ids))})
    assert resp.status_code == 200
    assert "Nguyễn Văn A" in resp.text and "Nguyễn Văn Á" in resp.text


def test_review_page_redirects_when_group_gone(client: TestClient):
    _login(client)
    resp = client.get("/cdc/loc-trung/xem", params={"entity": "case", "ids": "999997,999998"}, follow_redirects=False)
    assert resp.status_code == 303
    assert "loc-trung" in resp.headers["location"]


def test_merge_group_success(client: TestClient, tmp_path: Path):
    _login(client)
    _seed_dup_cases(tmp_path)
    ids = _dup_case_ids()
    keep_id = ids[0]
    csrf = _fresh_csrf(client, "/cdc/loc-trung/xem?entity=case&ids=" + ",".join(map(str, ids)))
    resp = client.post("/cdc/loc-trung/hop-nhat", data={
        "csrf_token": csrf, "entity": "case", "ids": [str(i) for i in ids], "keep": str(keep_id),
        "field__full_name": "Nguyễn Văn A", "field__case_code": "CA-DUP",
    }, follow_redirects=False)
    assert resp.status_code == 303
    remaining, _ = core.query_records("case", db_path=core.DB_PATH)
    assert sorted(r["id"] for r in remaining if r["case_code"] == "CA-DUP") == [keep_id]
    kept = next(r for r in remaining if r["id"] == keep_id)
    assert kept["full_name"] == "Nguyễn Văn A"


def test_merge_group_requires_role(client: TestClient, tmp_path: Path):
    _login(client, role=core.CDC_ROLE_VIEWER)
    _seed_dup_cases(tmp_path)
    ids = _dup_case_ids()
    csrf = _fresh_csrf(client, "/cdc/loc-trung/xem?entity=case&ids=" + ",".join(map(str, ids)))
    resp = client.post("/cdc/loc-trung/hop-nhat", data={
        "csrf_token": csrf, "entity": "case", "ids": [str(i) for i in ids], "keep": str(ids[0]),
    })
    assert resp.status_code == 403


def test_merge_group_rejects_bad_csrf(client: TestClient, tmp_path: Path):
    _login(client)
    _seed_dup_cases(tmp_path)
    ids = _dup_case_ids()
    resp = client.post("/cdc/loc-trung/hop-nhat", data={
        "csrf_token": "sai", "entity": "case", "ids": [str(i) for i in ids], "keep": str(ids[0]),
    })
    assert resp.status_code == 403


# ---------- Thùng rác / lịch sử ----------

def test_history_and_restore(client: TestClient, tmp_path: Path):
    _login(client)
    _seed_dup_cases(tmp_path)
    ids = _dup_case_ids()
    keep_id = ids[0]
    result = core.merge_duplicate_records("case", keep_id, [i for i in ids if i != keep_id], db_path=core.DB_PATH, actor="test")

    resp = client.get("/cdc/loc-trung/lich-su")
    assert resp.status_code == 200 and "Khôi phục" in resp.text

    csrf = _fresh_csrf(client, "/cdc/loc-trung/lich-su")
    restore_resp = client.post(f"/cdc/loc-trung/khoi-phuc/{result['action_id']}", data={"csrf_token": csrf}, follow_redirects=False)
    assert restore_resp.status_code == 303
    remaining, _ = core.query_records("case", db_path=core.DB_PATH)
    assert len([r for r in remaining if r["case_code"] == "CA-DUP"]) == 2


def test_restore_requires_admin_role(client: TestClient, tmp_path: Path):
    _login(client, role=core.CDC_ROLE_DATA_OPERATOR)
    _seed_dup_cases(tmp_path)
    ids = _dup_case_ids()
    result = core.merge_duplicate_records("case", ids[0], [ids[1]], db_path=core.DB_PATH, actor="test")
    csrf = _fresh_csrf(client, "/cdc/loc-trung/lich-su")
    resp = client.post(f"/cdc/loc-trung/khoi-phuc/{result['action_id']}", data={"csrf_token": csrf})
    assert resp.status_code == 403


# ---------- Tiêu chí ----------

def test_criteria_page_requires_admin(client: TestClient):
    _login(client, role=core.CDC_ROLE_DATA_OPERATOR)
    resp = client.get("/cdc/loc-trung/tieu-chi")
    assert resp.status_code == 403


def test_save_case_criteria(client: TestClient):
    _login(client)
    csrf = _fresh_csrf(client, "/cdc/loc-trung/tieu-chi?entity=case")
    resp = client.post("/cdc/loc-trung/tieu-chi", data={
        "csrf_token": csrf, "entity": "case", "enabled": ["name_commune"],
        "name_similarity_percent": "90", "onset_max_days": "5",
    }, follow_redirects=False)
    assert resp.status_code == 303
    saved = duplicate_config.load_case_criteria()
    assert saved.enabled == ["name_commune"]
    assert saved.onset_max_days == 5


def test_save_outbreak_rules(client: TestClient):
    _login(client)
    csrf = _fresh_csrf(client, "/cdc/loc-trung/tieu-chi?entity=outbreak")
    resp = client.post("/cdc/loc-trung/tieu-chi", data={
        "csrf_token": csrf, "entity": "outbreak", "min_score": "70", "definite_score": "90",
        **{f"weight__{k}": str(v) for k, v in duplicate_config.DEFAULT_OUTBREAK_WEIGHTS.items()},
    }, follow_redirects=False)
    assert resp.status_code == 303
    saved = duplicate_config.load_rules()
    assert saved.min_score == 70 and saved.definite_score == 90
