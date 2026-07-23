"""Mở rộng hàng đợi cho Web App Giai đoạn 3 (xem TASKS.md): chống gửi trùng theo nội dung,
lọc theo tuần/nguồn, "nhập lại" mục lỗi, xoá mục hàng đợi."""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pytest
from openpyxl import Workbook

import core


def make_excel_bytes(case_code: str) -> bytes:
    wb = Workbook(); ws = wb.active; ws.title = "Disease Cases"
    ws.append([label for label, _ in core.CASE_FIELDS])
    row = {key: "" for _, key in core.CASE_FIELDS}
    row["case_code"] = case_code
    row["full_name"] = "Nguyễn Văn Test"
    row["commune"] = "Xã Gia Viên"
    ws.append([row.get(key, "") for _, key in core.CASE_FIELDS])
    buf = io.BytesIO(); wb.save(buf)
    return buf.getvalue()


@pytest.fixture()
def db(tmp_path: Path):
    core.BACKUP_DIR = tmp_path / "backups"
    core.QUEUE_DIR = tmp_path / "queue"
    return tmp_path / "test.db"


def test_duplicate_content_returns_existing_queue_id(db: Path):
    data = make_excel_bytes("CA-001")
    first = core.queue_submit("Xã Gia Viên", "2026-W29", "ds.xlsx", data, db_path=db)
    assert first["duplicate"] is False
    second = core.queue_submit("Xã Gia Viên", "2026-W29", "ds.xlsx", data, db_path=db)
    assert second["duplicate"] is True
    assert second["queue_id"] == first["queue_id"]
    # Không tạo thêm dòng nào trong hàng đợi.
    assert len(core.list_import_queue(db_path=db)) == 1


def test_different_content_same_commune_week_creates_new_entry(db: Path):
    first = core.queue_submit("Xã Gia Viên", "2026-W29", "ds.xlsx", make_excel_bytes("CA-001"), db_path=db)
    second = core.queue_submit("Xã Gia Viên", "2026-W29", "ds.xlsx", make_excel_bytes("CA-002"), db_path=db)
    assert first["queue_id"] != second["queue_id"]
    assert len(core.list_import_queue(db_path=db)) == 2


def test_duplicate_check_ignores_failed_entries(db: Path):
    """Một mục đã bị đánh dấu lỗi (loi) không được coi là "đã nộp" — gửi lại cùng nội dung phải
    tạo dòng mới, không lặng lẽ trả về mục lỗi cũ."""
    data = make_excel_bytes("CA-001")
    first = core.queue_submit("Xã Gia Viên", "2026-W29", "ds.xlsx", data, db_path=db)
    with core._connect(db) as conn:
        conn.execute("UPDATE import_queue SET status='loi' WHERE id=?", (first["queue_id"],))
    second = core.queue_submit("Xã Gia Viên", "2026-W29", "ds.xlsx", data, db_path=db)
    assert second["duplicate"] is False
    assert second["queue_id"] != first["queue_id"]


def test_list_import_queue_filters_by_week_and_source(db: Path):
    core.queue_submit("Xã A", "2026-W20", "a.xlsx", make_excel_bytes("A1"), source="server_chinh", db_path=db)
    core.queue_submit("Xã A", "2026-W21", "a2.xlsx", make_excel_bytes("A2"), source="server_chinh", db_path=db)
    core.queue_submit("Xã B", "2026-W20", "b.xlsx", make_excel_bytes("B1"), source="server_phu", db_path=db)

    by_week = core.list_import_queue(week="2026-W20", db_path=db)
    assert {item["file_name"] for item in by_week} == {"a.xlsx", "b.xlsx"}

    by_source = core.list_import_queue(source="server_phu", db_path=db)
    assert [item["file_name"] for item in by_source] == ["b.xlsx"]

    combined = core.list_import_queue(week="2026-W20", source="server_chinh", db_path=db)
    assert [item["file_name"] for item in combined] == ["a.xlsx"]


def test_reimport_after_failure(db: Path):
    """Nộp 1 file KHÔNG hợp lệ (sai tiêu đề) để import_excel thất bại thật -> trạng thái loi ->
    sửa lại file hợp lệ trong hàng đợi rồi "nhập lại" phải thành công."""
    wb = Workbook(); ws = wb.active; ws.append(["Cột sai hoàn toàn"])
    buf = io.BytesIO(); wb.save(buf)
    bad_data = buf.getvalue()
    submitted = core.queue_submit("Xã Gia Viên", "2026-W29", "ds.xlsx", bad_data, db_path=db)

    with pytest.raises(Exception):
        core.import_queue_item(submitted["queue_id"], db_path=db)
    item = core.list_import_queue(db_path=db)[0]
    assert item["status"] == "loi"

    # CDC "sửa" file trực tiếp trên đĩa (giả lập việc thay file hợp lệ vào đúng đường dẫn).
    Path(item["file_path"]).write_bytes(make_excel_bytes("CA-FIXED"))
    result = core.import_queue_item(submitted["queue_id"], db_path=db)
    assert result["inserted"] == 1
    item_after = core.list_import_queue(db_path=db)[0]
    assert item_after["status"] == "da_nhap"


def test_reimport_rejects_when_already_being_processed(db: Path):
    data = make_excel_bytes("CA-001")
    submitted = core.queue_submit("Xã Gia Viên", "2026-W29", "ds.xlsx", data, db_path=db)
    with core._connect(db) as conn:
        conn.execute("UPDATE import_queue SET status='dang_nhap' WHERE id=?", (submitted["queue_id"],))
    with pytest.raises(ValueError, match="đang được xử lý"):
        core.import_queue_item(submitted["queue_id"], db_path=db)


def test_delete_queue_item_removes_row_and_file(db: Path):
    data = make_excel_bytes("CA-001")
    submitted = core.queue_submit("Xã Gia Viên", "2026-W29", "ds.xlsx", data, db_path=db)
    file_path = Path(core.list_import_queue(db_path=db)[0]["file_path"])
    assert file_path.exists()

    core.delete_queue_item(submitted["queue_id"], db_path=db, actor="cdc_test")
    assert core.list_import_queue(db_path=db) == []
    assert not file_path.exists()


def test_delete_queue_item_rejects_already_imported(db: Path):
    data = make_excel_bytes("CA-001")
    submitted = core.queue_submit("Xã Gia Viên", "2026-W29", "ds.xlsx", data, db_path=db)
    core.import_queue_item(submitted["queue_id"], db_path=db)
    with pytest.raises(ValueError, match="đã nhập"):
        core.delete_queue_item(submitted["queue_id"], db_path=db)


def test_delete_queue_item_rejects_in_progress(db: Path):
    data = make_excel_bytes("CA-001")
    submitted = core.queue_submit("Xã Gia Viên", "2026-W29", "ds.xlsx", data, db_path=db)
    with core._connect(db) as conn:
        conn.execute("UPDATE import_queue SET status='dang_nhap' WHERE id=?", (submitted["queue_id"],))
    with pytest.raises(ValueError, match="đang được xử lý"):
        core.delete_queue_item(submitted["queue_id"], db_path=db)


def test_delete_queue_item_missing_raises(db: Path):
    with pytest.raises(ValueError, match="Không tìm thấy"):
        core.delete_queue_item(999999, db_path=db)
