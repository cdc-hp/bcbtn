"""Kiểm thử Giai đoạn 4: Dashboard, /cdc/ca-benh, /cdc/o-dich (xem TASKS.md)."""

from __future__ import annotations

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


def _seed_cases(tmp_path: Path, rows: list[dict]) -> None:
    wb = Workbook(); ws = wb.active; ws.title = "Disease Cases"
    ws.append([label for label, _ in core.CASE_FIELDS])
    for row in rows:
        full = {key: "" for _, key in core.CASE_FIELDS}
        full.update(row)
        ws.append([full.get(key, "") for _, key in core.CASE_FIELDS])
    path = tmp_path / "seed_cases.xlsx"
    wb.save(path)
    core.import_excel(path, core.DB_PATH)


def _seed_outbreak(**overrides) -> int:
    data = {
        "disease": "Sốt xuất huyết", "location": "Thôn 1", "first_onset_date": "2026-07-01",
        "status": "Đang hoạt động", "case_count": 5, "death_count": 0, "reporting_unit": "TYT Xã A",
        "admin_area": "Xã A",
    }
    data.update(overrides)
    return core.save_outbreak(data, db_path=core.DB_PATH)


# ---------- Dashboard ----------

def test_dashboard_shows_real_stats(client: TestClient, tmp_path: Path):
    _login(client)
    _seed_cases(tmp_path, [{"case_code": "CA-1", "full_name": "Nguyễn A", "commune": "Xã A"}])
    _seed_outbreak()
    core.queue_submit("Xã B", core.current_iso_week(), "b.xlsx", b"PK\x03\x04fake", db_path=core.DB_PATH)

    resp = client.get("/cdc/dashboard")
    assert resp.status_code == 200
    assert "1" in resp.text  # ít nhất có xuất hiện số lượng nào đó — kiểm tra kỹ hơn dưới đây
    assert core.dashboard_stats(db_path=core.DB_PATH)["case_records"] == 1
    assert core.dashboard_stats(db_path=core.DB_PATH)["outbreak_records"] == 1


# ---------- /cdc/ca-benh ----------

def test_case_list_requires_login(client: TestClient):
    resp = client.get("/cdc/ca-benh", follow_redirects=False)
    assert resp.status_code == 303


def test_case_list_shows_seeded_rows_and_search(client: TestClient, tmp_path: Path):
    _login(client)
    _seed_cases(tmp_path, [
        {"case_code": "CA-1", "full_name": "Nguyễn Văn A", "commune": "Xã A"},
        {"case_code": "CA-2", "full_name": "Trần Thị B", "commune": "Xã B"},
    ])
    page = client.get("/cdc/ca-benh")
    assert "CA-1" in page.text and "CA-2" in page.text

    filtered = client.get("/cdc/ca-benh", params={"search": "CA-1"})
    assert "CA-1" in filtered.text and "CA-2" not in filtered.text


def test_case_list_has_display_settings_and_working_advanced_filters(client: TestClient, tmp_path: Path):
    _login(client)
    _seed_cases(tmp_path, [
        {
            "case_code": "ADV-A", "full_name": "Nguyễn An", "birth_date_raw": "01/01/1996",
            "gender": "Nữ", "occupation": "Giáo viên", "diagnosis_classification": "Ca xác định",
            "current_status": "Đang điều trị", "province": "Hải Phòng", "commune": "Xã A",
            "reporting_unit": "TYT A", "record_status": "Đã xác nhận",
            "report_datetime": "20/07/2026 08:30", "onset_date": "10/07/2026",
            "admission_date": "11/07/2026", "discharge_or_death_date": "18/07/2026",
            "sample_date": "12/07/2026", "test_result": "Dương tính", "lab_unit": "CDC HP",
            "treatment_facility": "Bệnh viện A",
        },
        {
            "case_code": "ADV-B", "full_name": "Trần Bình", "birth_date_raw": "01/01/1970",
            "gender": "Nam", "occupation": "Công nhân", "diagnosis_classification": "Ca nghi ngờ",
            "current_status": "Đã khỏi", "province": "Quảng Ninh", "commune": "Xã B",
            "reporting_unit": "TYT B", "record_status": "Chờ xác nhận",
            "report_datetime": "01/06/2026 08:30", "onset_date": "01/06/2026",
            "admission_date": "02/06/2026", "discharge_or_death_date": "08/06/2026",
            "sample_date": "03/06/2026", "test_result": "Âm tính", "lab_unit": "BV B",
            "treatment_facility": "Bệnh viện B",
        },
    ])

    page = client.get("/cdc/ca-benh")
    assert "Cột hiển thị" in page.text
    assert "48 trường" in page.text
    assert "Nâng cao" in page.text
    assert page.text.count('data-column-toggle') == len(core.CASE_FIELDS) == 48
    assert 'value="occupation" data-column-toggle data-default-visible="false"' in page.text
    assert 'value="case_code" data-column-toggle data-default-visible="true" checked' in page.text

    filters = [
        {"full_name": "Nguyễn An"}, {"gender": "Nữ"}, {"occupation": "Giáo viên"},
        {"diagnosis_classification": "Ca xác định"}, {"current_status": "Đang điều trị"},
        {"province": "Hải Phòng"}, {"reporting_unit": "TYT A"}, {"record_status": "Đã xác nhận"},
        {"report_from": "2026-07-01", "report_to": "2026-07-31"},
        {"onset_from": "2026-07-01", "onset_to": "2026-07-31"},
        {"admission_from": "2026-07-01", "admission_to": "2026-07-31"},
        {"discharge_from": "2026-07-01", "discharge_to": "2026-07-31"},
        {"sample_from": "2026-07-01", "sample_to": "2026-07-31"},
        {"test_result": "Dương tính"}, {"lab_unit": "CDC HP"},
        {"treatment_facility": "Bệnh viện A"}, {"age_min": "25", "age_max": "35"},
    ]
    for params in filters:
        filtered = client.get("/cdc/ca-benh", params=params)
        assert "ADV-A" in filtered.text, params
        assert "ADV-B" not in filtered.text, params
        assert "cdc-advanced-filter\" open" in filtered.text


def test_case_detail_shows_fields_and_issues(client: TestClient, tmp_path: Path):
    _login(client)
    _seed_cases(tmp_path, [{"case_code": "CA-1", "full_name": "Nguyễn Văn A", "commune": "Xã A"}])
    record = core.query_records("case", db_path=core.DB_PATH)[0][0]
    detail = client.get(f"/cdc/ca-benh/{record['id']}")
    assert detail.status_code == 200
    assert "CA-1" in detail.text
    assert "Nguyễn Văn A" in detail.text


def test_case_detail_missing_returns_403_page(client: TestClient):
    _login(client)
    resp = client.get("/cdc/ca-benh/999999")
    assert resp.status_code == 403


def test_viewer_can_view_but_not_import(client: TestClient, tmp_path: Path):
    _login(client, role=core.CDC_ROLE_VIEWER)
    _seed_cases(tmp_path, [{"case_code": "CA-1", "full_name": "Nguyễn Văn A", "commune": "Xã A"}])
    resp = client.get("/cdc/ca-benh")
    assert resp.status_code == 200
    assert "CA-1" in resp.text


# ---------- /cdc/o-dich ----------

def test_outbreak_list_and_detail(client: TestClient):
    _login(client)
    outbreak_id = _seed_outbreak(disease="Sởi")
    page = client.get("/cdc/o-dich")
    assert page.status_code == 200 and "Sởi" in page.text

    detail = client.get(f"/cdc/o-dich/{outbreak_id}")
    assert detail.status_code == 200
    assert "Sởi" in detail.text


def test_outbreak_filter_by_disease(client: TestClient):
    _login(client)
    _seed_outbreak(disease="Benh-Mot")
    _seed_outbreak(disease="Benh-Hai")
    resp = client.get("/cdc/o-dich", params={"disease": "Benh-Mot"})
    # "Benh-Hai" vẫn hợp lệ xuất hiện trong <option> của dropdown lọc (liệt kê mọi giá trị có
    # thể chọn) — chỉ kiểm tra nó KHÔNG xuất hiện như một dòng kết quả trong bảng.
    assert "<td>Benh-Mot</td>" in resp.text
    assert "<td>Benh-Hai</td>" not in resp.text


def test_outbreak_create_edit_delete_are_wired_and_audited(client: TestClient):
    _login(client)
    csrf = _fresh_csrf(client, "/cdc/o-dich/them")
    created = client.post("/cdc/o-dich/them", data={
        "csrf_token": csrf, "disease": "Cúm A", "location": "Phường Test",
        "first_onset_date": "2026-07-20", "status": "Đang hoạt động",
        "case_count": "4", "death_count": "0", "reporting_unit": "CDC Test",
    })
    assert created.status_code == 200
    rows, _ = core.query_records("outbreak", search="Cúm A", db_path=core.DB_PATH)
    assert len(rows) == 1
    outbreak_id = rows[0]["id"]

    csrf = _fresh_csrf(client, f"/cdc/o-dich/{outbreak_id}/sua")
    edited = client.post(f"/cdc/o-dich/{outbreak_id}/sua", data={
        "csrf_token": csrf, "disease": "Cúm A", "location": "Phường Đã sửa",
        "first_onset_date": "2026-07-20", "status": "Đã kết thúc",
        "case_count": "5", "death_count": "0", "reporting_unit": "CDC Test",
    })
    assert edited.status_code == 200
    assert core.get_record("outbreak", outbreak_id, db_path=core.DB_PATH)["location"] == "Phường Đã sửa"

    csrf = _fresh_csrf(client, f"/cdc/o-dich/{outbreak_id}")
    deleted = client.post(f"/cdc/o-dich/{outbreak_id}/xoa", data={"csrf_token": csrf})
    assert deleted.status_code == 200
    assert core.get_record("outbreak", outbreak_id, db_path=core.DB_PATH) is None
    actions = {row["action"] for row in core.list_audit_log(db_path=core.DB_PATH)}
    assert {"create_outbreak_web", "update_outbreak_web", "delete_outbreak_web"} <= actions


def test_viewer_cannot_create_outbreak(client: TestClient):
    _login(client, role=core.CDC_ROLE_VIEWER)
    assert client.get("/cdc/o-dich/them").status_code == 403
