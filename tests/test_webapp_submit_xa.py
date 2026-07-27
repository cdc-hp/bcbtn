"""Kiểm thử POST /queue/submit-xa — đường nộp trực tiếp từ trình duyệt xã (trang GitHub Pages),
khác /queue/submit (Google Apps Script gọi) ở khoá xác thực riêng (`public_submit_key`) và tự
kiểm tra lại xã/tuần/định dạng file vì không còn Apps Script đứng giữa chặn trước. Xem CLAUDE.md
mục "Web nộp báo cáo trực tiếp từ GitHub Pages"."""

from __future__ import annotations

import base64
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

import core
import deployment_config
from deployment_config import save_config


def make_excel_b64(case_code: str) -> str:
    wb = Workbook(); ws = wb.active; ws.title = "Disease Cases"
    ws.append([label for label, _ in core.CASE_FIELDS])
    row = {key: "" for _, key in core.CASE_FIELDS}
    row["case_code"] = case_code
    row["full_name"] = "Nguyễn Văn Test"
    row["commune"] = "Phường Gia Viên"
    ws.append([row.get(key, "") for _, key in core.CASE_FIELDS])
    buf = io.BytesIO(); wb.save(buf)
    return base64.b64encode(buf.getvalue()).decode("ascii")


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(core, "DATA_DIR", tmp_path / "data")
    core.DATA_DIR.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(core, "DB_PATH", core.DATA_DIR / "test.db")
    monkeypatch.setattr(core, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(core, "QUEUE_DIR", tmp_path / "queue")
    monkeypatch.setattr(deployment_config, "CONFIG_PATH", tmp_path / "deployment.json")

    from webapp.services.rate_limit import queue_submit_limiter
    queue_submit_limiter._hits.clear()

    import webapp.main as webapp_main
    return TestClient(webapp_main.app)


def _set_public_submit_key(key: str) -> None:
    cfg = deployment_config.load_config()
    cfg.public_submit_key = key
    save_config(cfg)


VALID_PAYLOAD = {
    "commune": "Phường Gia Viên", "week": "2026-W29", "file_name": "ds.xlsx",
    "submitted_by": "Y tá A",
}


def test_submit_xa_rejected_when_key_not_configured(client: TestClient):
    resp = client.post(
        "/queue/submit-xa", json=dict(VALID_PAYLOAD, content_base64=make_excel_b64("C1")),
    )
    assert resp.status_code == 503
    assert resp.json()["ok"] is False


def test_submit_xa_rejected_with_wrong_key(client: TestClient):
    _set_public_submit_key("khoa-xa")
    resp = client.post(
        "/queue/submit-xa", json=dict(VALID_PAYLOAD, content_base64=make_excel_b64("C1")),
        headers={"X-GSBTN-Password": "sai"},
    )
    assert resp.status_code == 401


def test_submit_xa_success_creates_queue_entry(client: TestClient):
    _set_public_submit_key("khoa-xa")
    resp = client.post(
        "/queue/submit-xa", json=dict(VALID_PAYLOAD, content_base64=make_excel_b64("C1")),
        headers={"X-GSBTN-Password": "khoa-xa"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["result"]["duplicate"] is False
    items = core.list_import_queue(db_path=core.DB_PATH)
    assert len(items) == 1
    assert items[0]["source"] == "server_chinh"


def test_submit_xa_rejects_commune_not_in_official_list(client: TestClient):
    _set_public_submit_key("khoa-xa")
    resp = client.post(
        "/queue/submit-xa",
        json=dict(VALID_PAYLOAD, commune="Xã Không Tồn Tại", content_base64=make_excel_b64("C1")),
        headers={"X-GSBTN-Password": "khoa-xa"},
    )
    assert resp.status_code == 400
    assert core.list_import_queue(db_path=core.DB_PATH) == []


def test_submit_xa_rejects_future_week(client: TestClient):
    _set_public_submit_key("khoa-xa")
    resp = client.post(
        "/queue/submit-xa",
        json=dict(VALID_PAYLOAD, week="2999-W01", content_base64=make_excel_b64("C1")),
        headers={"X-GSBTN-Password": "khoa-xa"},
    )
    assert resp.status_code == 400


def test_submit_xa_rejects_bad_week_format(client: TestClient):
    _set_public_submit_key("khoa-xa")
    resp = client.post(
        "/queue/submit-xa",
        json=dict(VALID_PAYLOAD, week="tuan-29", content_base64=make_excel_b64("C1")),
        headers={"X-GSBTN-Password": "khoa-xa"},
    )
    assert resp.status_code == 400


def test_submit_xa_rejects_non_xlsx_signature(client: TestClient):
    _set_public_submit_key("khoa-xa")
    fake_content = base64.b64encode(b"khong phai file excel").decode("ascii")
    resp = client.post(
        "/queue/submit-xa", json=dict(VALID_PAYLOAD, content_base64=fake_content),
        headers={"X-GSBTN-Password": "khoa-xa"},
    )
    assert resp.status_code == 400


def test_submit_xa_rate_limited_after_threshold(client: TestClient):
    _set_public_submit_key("khoa-xa")
    for i in range(10):
        resp = client.post(
            "/queue/submit-xa",
            json=dict(VALID_PAYLOAD, file_name=f"{i}.xlsx", content_base64=make_excel_b64(f"C{i}")),
            headers={"X-GSBTN-Password": "khoa-xa"},
        )
        assert resp.status_code == 200
    over_limit = client.post(
        "/queue/submit-xa",
        json=dict(VALID_PAYLOAD, file_name="over.xlsx", content_base64=make_excel_b64("C-over")),
        headers={"X-GSBTN-Password": "khoa-xa"},
    )
    assert over_limit.status_code == 429


def test_submit_xa_cors_preflight_allows_public_frontend_origin(client: TestClient):
    resp = client.options(
        "/queue/submit-xa",
        headers={
            "Origin": "https://cdc-hp.github.io",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-gsbtn-password",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "https://cdc-hp.github.io"


def test_submit_xa_cors_rejects_other_origins(client: TestClient):
    resp = client.options(
        "/queue/submit-xa",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-gsbtn-password",
        },
    )
    assert "access-control-allow-origin" not in resp.headers
