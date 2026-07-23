"""Kiểm thử Giai đoạn 5 ở tầng core.py: get_records_by_ids, count_duplicate_groups
(xem TASKS.md)."""

from __future__ import annotations

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
    # Mặc định (case_code, national_id) không khớp vì cả hai đều trống -> không phát hiện trùng.
    assert core.count_duplicate_groups("case", db_path=db) == 0
    duplicate_config.save_case_criteria(duplicate_config.CaseDuplicateCriteria(enabled=["name_commune"]))
    assert core.count_duplicate_groups("case", db_path=db) == 1
