"""Truy vấn ca bệnh cho các bộ lọc chi tiết chỉ có trên giao diện Web.

Module nằm trong ``webapp`` để không thay đổi API/nghiệp vụ trong ``core.py``. Tất cả tên
cột được lấy từ danh sách cố định bên dưới; giá trị người dùng luôn đi qua tham số SQLite.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

import core


CASE_ADVANCED_KEYS = (
    "full_name", "gender", "occupation", "diagnosis_classification", "current_status",
    "province", "reporting_unit", "record_status", "report_from", "report_to",
    "onset_from", "onset_to", "admission_from", "admission_to", "discharge_from",
    "discharge_to", "sample_from", "sample_to", "test_result", "lab_unit",
    "treatment_facility", "age_min", "age_max",
)

CASE_OPTION_FIELDS = (
    "gender", "occupation", "diagnosis_classification", "current_status", "province",
    "reporting_unit", "record_status", "test_result", "lab_unit", "treatment_facility",
)

_EXACT_FIELDS = {
    "gender", "occupation", "diagnosis_classification", "current_status", "province",
    "reporting_unit", "record_status", "test_result", "lab_unit", "treatment_facility",
}

_DATE_RANGES = {
    "report": "report_datetime",
    "onset": "onset_date",
    "admission": "admission_date",
    "discharge": "discharge_or_death_date",
    "sample": "sample_date",
}


def clean_case_filters(values: Mapping[str, Any]) -> dict[str, str]:
    """Chỉ giữ tham số được hỗ trợ và chuẩn hóa thành chuỗi đã bỏ khoảng trắng."""
    return {key: str(values.get(key, "") or "").strip() for key in CASE_ADVANCED_KEYS}


def has_advanced_filters(filters: Mapping[str, str]) -> bool:
    return any(filters.get(key, "") for key in CASE_ADVANCED_KEYS)


def _valid_iso_date(value: str) -> str:
    if not value:
        return ""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return ""


def _age(value: str) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if 0 <= parsed <= 130 else None


def _where_clause(
    *, search: str = "", disease: str = "", status: str = "", admin_area: str = "",
    advanced: Mapping[str, str] | None = None,
) -> tuple[str, list[Any]]:
    where: list[str] = []
    params: list[Any] = []
    if search:
        like = f"%{search}%"
        where.append("(full_name LIKE ? OR case_code LIKE ? OR national_id LIKE ? OR current_address LIKE ? OR commune LIKE ?)")
        params.extend([like] * 5)
    if disease:
        where.append("main_diagnosis = ?")
        params.append(disease)
    if status:
        where.append("(record_status = ? OR current_status = ?)")
        params.extend([status, status])
    if admin_area:
        where.append("commune = ?")
        params.append(admin_area)

    filters = clean_case_filters(advanced or {})
    if filters["full_name"]:
        where.append("full_name LIKE ?")
        params.append(f"%{filters['full_name']}%")
    for field in _EXACT_FIELDS:
        if filters[field]:
            where.append(f"{field} = ?")
            params.append(filters[field])
    for prefix, field in _DATE_RANGES.items():
        start = _valid_iso_date(filters[f"{prefix}_from"])
        end = _valid_iso_date(filters[f"{prefix}_to"])
        if start:
            where.append(f"substr({field}, 1, 10) >= ?")
            params.append(start)
        if end:
            where.append(f"substr({field}, 1, 10) <= ?")
            params.append(end)

    age_min = _age(filters["age_min"])
    age_max = _age(filters["age_max"])
    current_year = datetime.now().year
    if age_min is not None:
        where.append("birth_year <= ?")
        params.append(current_year - age_min)
    if age_max is not None:
        where.append("birth_year >= ?")
        params.append(current_year - age_max)

    return (" WHERE " + " AND ".join(where) if where else ""), params


def _connect(db_path: Path | str) -> sqlite3.Connection:
    core.init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def query_cases(
    *, search: str = "", disease: str = "", status: str = "", admin_area: str = "",
    advanced: Mapping[str, str] | None = None, page: int = 1, page_size: int = 50,
    sort: str = "", direction: str = "desc",
    db_path: Path | str = core.DB_PATH,
) -> tuple[list[dict[str, Any]], int]:
    where_sql, params = _where_clause(
        search=search, disease=disease, status=status, admin_area=admin_area, advanced=advanced,
    )
    page = max(1, page)
    page_size = max(10, min(2000, page_size))
    allowed_sort = set(core.CASE_TABLE_COLUMNS)
    sort_field = sort if sort in allowed_sort else "onset_date"
    sort_direction = "ASC" if direction.lower() == "asc" else "DESC"
    with _connect(db_path) as conn:
        total = int(conn.execute(f"SELECT COUNT(*) FROM cases{where_sql}", params).fetchone()[0])
        rows = conn.execute(
            f"SELECT {','.join(core.CASE_TABLE_COLUMNS)} FROM cases{where_sql} "
            f"ORDER BY {sort_field} {sort_direction}, id DESC LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
    return [dict(row) for row in rows], total


def list_case_options(db_path: Path | str = core.DB_PATH) -> dict[str, list[str]]:
    return {field: core.list_filter_values("case", field, db_path=db_path) for field in CASE_OPTION_FIELDS}


def export_cases(
    path: Path | str, *, search: str = "", disease: str = "", status: str = "",
    admin_area: str = "", advanced: Mapping[str, str] | None = None,
    db_path: Path | str = core.DB_PATH,
) -> int:
    """Xuất cùng tập kết quả đang hiển thị khi người dùng dùng bộ lọc nâng cao."""
    where_sql, params = _where_clause(
        search=search, disease=disease, status=status, admin_area=admin_area, advanced=advanced,
    )
    hidden = {"row_hash", "raw_json"}
    with _connect(db_path) as conn:
        total = int(conn.execute(f"SELECT COUNT(*) FROM cases{where_sql}", params).fetchone()[0])
        if total == 0:
            raise ValueError("Không có dữ liệu phù hợp để xuất.")
        if total > 50_000:
            raise ValueError("Bộ lọc có trên 50.000 dòng. Hãy thu hẹp bộ lọc trước khi xuất.")
        db_columns = [
            row[1] for row in conn.execute("PRAGMA table_info(cases)").fetchall() if row[1] not in hidden
        ]
        rows = conn.execute(
            f"SELECT {','.join(db_columns)} FROM cases{where_sql} ORDER BY onset_date DESC, id DESC",
            params,
        ).fetchall()
    extra_labels = {
        "id": "ID", "birth_year": "Năm sinh", "source_file": "File nguồn",
        "source_sheet": "Sheet nguồn", "source_row": "Dòng nguồn", "imported_at": "Thời điểm nhập",
    }
    headers = [core.CASE_LABELS.get(column, extra_labels.get(column, column)) for column in db_columns]
    core.export_rows(path, headers, [[row[column] for column in db_columns] for row in rows])
    return total
