"""Kiểm thử Giai đoạn 5 ở tầng core.py: get_records_by_ids, count_duplicate_groups
(xem TASKS.md)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from openpyxl import Workbook

import core
import duplicate_config


@pytest.fixture()
def db(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "test.db"
    monkeypatch.setattr(core, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(duplicate_config, "CONFIG_PATH", tmp_path / "duplicate_rules.json")
    monkeypatch.setattr(duplicate_config, "CRITERIA_CONFIG_PATH", tmp_path / "case_duplicate_criteria.json")
    core.init_db(path)
    return path


def _seed_cases(tmp_path: Path, db: Path, rows: list[dict]) -> None:
    wb = Workbook(); ws = wb.active; ws.title = "Disease Cases"
    ws.append([label for label, _ in core.CASE_FIELDS])
    for row in rows:
        full = {key: "" for _, key in core.CASE_FIELDS}
        full.update(row)
        ws.append([full.get(key, "") for _, key in core.CASE_FIELDS])
    path = tmp_path / f"seed_{len(rows)}_{id(rows)}.xlsx"
    wb.save(path)
    core.import_excel(path, db)


def test_get_records_by_ids_preserves_order_and_skips_missing(tmp_path: Path, db: Path):
    _seed_cases(tmp_path, db, [
        {"case_code": "CA-1", "full_name": "Nguyễn Văn A"},
        {"case_code": "CA-2", "full_name": "Trần Thị B"},
        {"case_code": "CA-3", "full_name": "Lê Văn C"},
    ])
    rows, _ = core.query_records("case", db_path=db)
    by_code = {r["case_code"]: r["id"] for r in rows}
    id1, id2, id3 = by_code["CA-1"], by_code["CA-2"], by_code["CA-3"]

    records = core.get_records_by_ids("case", [id3, 999999, id1], db_path=db)
    assert [r["id"] for r in records] == [id3, id1]
    assert records[0]["case_code"] == "CA-3"


def test_get_records_by_ids_empty_list(db: Path):
    assert core.get_records_by_ids("case", [], db_path=db) == []


def test_count_duplicate_groups_case(tmp_path: Path, db: Path):
    _seed_cases(tmp_path, db, [
        {"case_code": "CA-DUP", "full_name": "Nguyễn Văn A"},
        {"case_code": "CA-DUP", "full_name": "Nguyễn Văn Á"},
        {"case_code": "CA-OTHER", "full_name": "Trần Thị B"},
    ])
    assert core.count_duplicate_groups("case", db_path=db) == 1


def test_count_duplicate_groups_outbreak(db: Path):
    core.save_outbreak({"disease": "Sởi", "location": "Thôn 1", "case_count": 1}, db_path=db)
    core.save_outbreak({"disease": "Sởi", "location": "Thôn 1", "case_count": 2}, db_path=db)
    assert core.count_duplicate_groups("outbreak", db_path=db) >= 1


def test_count_duplicate_groups_uses_saved_criteria(tmp_path: Path, db: Path):
    _seed_cases(tmp_path, db, [
        {"case_code": "", "full_name": "Nguyễn Văn A", "commune": "Xã A", "phone": "0900000001"},
        {"case_code": "", "full_name": "Nguyễn Văn A", "commune": "Xã A", "phone": "0900000002"},
    ])
    # Mặc định dùng case_code; giá trị trống không được dùng làm khóa trùng.
    assert core.count_duplicate_groups("case", db_path=db) == 0
    duplicate_config.save_case_criteria(duplicate_config.CaseDuplicateCriteria(enabled=["full_name", "commune"]))
    assert core.count_duplicate_groups("case", db_path=db) == 1


# ---------- Tự động gộp trùng khớp toàn bộ 48 trường ----------

def _clone_case_row(db_path: Path, case_id: int) -> int:
    """Sao y một ca bệnh thành bản ghi MỚI với `row_hash` khác (chỉ để vượt qua ràng buộc UNIQUE,
    không ảnh hưởng phát hiện trùng — auto_merge_exact_case_duplicates chỉ so 48 trường
    CASE_FIELDS) — mô phỏng đáng tin cậy 2 lần nộp cùng nội dung mà không phụ thuộc thời điểm
    thực (2 lần import_excel trong cùng 1 giây sẽ bị row_hash chặn ngay từ khi nhập vì
    imported_at cũng nằm trong dữ liệu tính hash)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = dict(conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone())
        row.pop("id")
        row["row_hash"] = str(row["row_hash"]) + ":clone"
        cols = list(row)
        cur = conn.execute(
            f"INSERT INTO cases ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
            [row[c] for c in cols],
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def test_auto_merge_exact_case_duplicates(tmp_path: Path, db: Path):
    row = {
        "case_code": "CA-EXACT", "full_name": "Nguyễn Văn A", "commune": "Xã A",
        "phone": "0900000001", "main_diagnosis": "Cúm",
    }
    _seed_cases(tmp_path, db, [row])
    _seed_cases(tmp_path, db, [{"case_code": "CA-OTHER", "full_name": "Trần Thị B"}])
    rows, _ = core.query_records("case", db_path=db)
    original_id = next(r["id"] for r in rows if r["case_code"] == "CA-EXACT")
    clone_id = _clone_case_row(db, original_id)
    exact_ids = sorted([original_id, clone_id])

    result = core.auto_merge_exact_case_duplicates(db_path=db, actor="test")
    assert result["merged_groups"] == 1
    assert result["removed_count"] == 1

    remaining, _ = core.query_records("case", db_path=db)
    remaining_exact = [r for r in remaining if r["case_code"] == "CA-EXACT"]
    assert len(remaining_exact) == 1
    assert remaining_exact[0]["id"] == exact_ids[0]  # giữ ca cũ (ID nhỏ hơn)
    assert any(r["case_code"] == "CA-OTHER" for r in remaining)

    actions = core.list_duplicate_actions(db_path=db)
    auto_action = next(a for a in actions if a["action_type"] == "auto_merge_exact")
    assert auto_action["keep_id"] == exact_ids[0]

    # Không còn gì để gộp thêm — chạy lại phải là no-op (idempotent).
    again = core.auto_merge_exact_case_duplicates(db_path=db, actor="test")
    assert again == {"merged_groups": 0, "removed_count": 0}


def test_auto_merge_exact_case_duplicates_ignores_partial_matches(tmp_path: Path, db: Path):
    _seed_cases(tmp_path, db, [{"case_code": "CA-DUP", "full_name": "Nguyễn Văn A", "phone": "0900000001"}])
    _seed_cases(tmp_path, db, [{"case_code": "CA-DUP", "full_name": "Nguyễn Văn A", "phone": "0900000002"}])
    result = core.auto_merge_exact_case_duplicates(db_path=db, actor="test")
    assert result == {"merged_groups": 0, "removed_count": 0}
    rows, _ = core.query_records("case", db_path=db)
    assert len([r for r in rows if r["case_code"] == "CA-DUP"]) == 2


def test_auto_merge_exact_case_duplicates_restorable(tmp_path: Path, db: Path):
    row = {"case_code": "CA-EXACT", "full_name": "Nguyễn Văn A", "commune": "Xã A"}
    _seed_cases(tmp_path, db, [row])
    rows, _ = core.query_records("case", db_path=db)
    original_id = next(r["id"] for r in rows if r["case_code"] == "CA-EXACT")
    _clone_case_row(db, original_id)
    core.auto_merge_exact_case_duplicates(db_path=db, actor="test")
    action = next(a for a in core.list_duplicate_actions(db_path=db) if a["action_type"] == "auto_merge_exact")

    core.restore_duplicate_action(action["id"], db_path=db, actor="test")
    remaining, _ = core.query_records("case", db_path=db)
    assert len([r for r in remaining if r["case_code"] == "CA-EXACT"]) == 2


# ---------- Gộp trùng cập nhật (giữ ID cũ, lấy giá trị bản ghi nhập mới nhất) ----------

def test_merge_duplicates_take_latest_keeps_old_id_and_uses_newest_values(tmp_path: Path, db: Path):
    _seed_cases(tmp_path, db, [{
        "case_code": "CA-A", "full_name": "Nguyen Van A", "commune": "Xa Cu",
        "main_diagnosis": "Cum", "phone": "0900000001",
    }])
    _seed_cases(tmp_path, db, [{
        "case_code": "CA-A", "full_name": "Nguyen Van A Moi", "commune": "Xa Moi",
        "main_diagnosis": "Sot xuat huyet", "phone": "0900000002",
    }])
    rows, _ = core.query_records("case", db_path=db)
    by_phone = {r["phone"]: r for r in rows if r["case_code"] == "CA-A"}
    older, newer = by_phone["0900000001"], by_phone["0900000002"]
    assert older["id"] < newer["id"]
    conn = sqlite3.connect(db)
    try:
        conn.execute("UPDATE cases SET imported_at=? WHERE id=?", ("2020-01-01 00:00:00", older["id"]))
        conn.execute("UPDATE cases SET imported_at=? WHERE id=?", ("2030-01-01 00:00:00", newer["id"]))
        conn.commit()
    finally:
        conn.close()

    result = core.merge_duplicates_take_latest("case", [older["id"], newer["id"]], db_path=db, actor="test")
    assert result["kept_id"] == older["id"]
    assert result["source_id"] == newer["id"]
    kept = core.get_record("case", older["id"], db_path=db)
    assert kept["full_name"] == "Nguyen Van A Moi"
    assert kept["commune"] == "Xa Moi"
    assert kept["main_diagnosis"] == "Sot xuat huyet"
    remaining, _ = core.query_records("case", db_path=db)
    assert sorted(r["id"] for r in remaining if r["case_code"] == "CA-A") == [older["id"]]


def test_merge_duplicates_take_latest_requires_two_ids(db: Path):
    with pytest.raises(ValueError):
        core.merge_duplicates_take_latest("case", [1], db_path=db)
