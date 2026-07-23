from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import core


def _user_data_root() -> Path:
    override = os.environ.get("GIAM_SAT_DICH_BENH_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "CDC_HaiPhong" / "GiamSatDichBenh"
    return Path.home() / ".giam_sat_dich_benh"


CONFIG_PATH = _user_data_root() / "case_view_config.json"

# Cột gốc có thể chọn để hiển thị: toàn bộ 48 trường CASE_FIELDS + birth_year (cột suy ra từ
# birth_date_raw lúc nhập, không nằm trong CASE_FIELDS nhưng vẫn là cột thật trong bảng cases).
AVAILABLE_BASE_FIELDS: list[tuple[str, str]] = [*core.CASE_FIELDS, ("Năm sinh", "birth_year")]
BASE_FIELD_LABELS: dict[str, str] = {db: label for label, db in AVAILABLE_BASE_FIELDS}

# Các mốc thời gian dùng được cho cột tính toán "Số ngày giữa 2 mốc" — chỉ những trường thật sự
# là ngày/thời gian trong danh sách ca bệnh (giao giữa DATE_FIELDS/DATETIME_FIELDS của core.py
# với các trường có trong CASE_FIELDS, vì 2 tập đó dùng chung cho cả ca bệnh lẫn ổ dịch).
_CASE_DB_FIELDS = {db for _, db in core.CASE_FIELDS}
DATE_LIKE_FIELDS: list[str] = [
    db for db in [*core.DATE_FIELDS, *core.DATETIME_FIELDS] if db in _CASE_DB_FIELDS
]

KIND_AGE = "age_years"
KIND_DAYS_BETWEEN = "days_between"
KIND_CONCAT = "concat"
COMPUTED_KINDS = [KIND_AGE, KIND_DAYS_BETWEEN, KIND_CONCAT]
COMPUTED_KIND_LABELS = {
    KIND_AGE: "Tuổi (tính từ năm sinh tới năm hiện tại)",
    KIND_DAYS_BETWEEN: "Số ngày giữa 2 mốc thời gian",
    KIND_CONCAT: "Nối nhiều cột thành 1 cột hiển thị",
}

DEFAULT_COLUMNS: list[tuple[str, str]] = [
    ("case_code", "Mã số"), ("full_name", "Họ tên"), ("birth_date_raw", "Ngày sinh"),
    ("gender", "Giới"), ("commune", "Xã/Phường"), ("main_diagnosis", "Chẩn đoán"),
    ("onset_date", "Khởi phát"), ("current_status", "Tình trạng"),
    ("report_datetime", "Báo cáo"), ("reporting_unit", "Đơn vị báo cáo"),
]


@dataclass
class ComputedColumn:
    """Cột hiển thị được tính từ (các) cột khác có sẵn trong dữ liệu ca bệnh — không phải cột
    lưu trong CSDL, chỉ tính lại mỗi lần hiển thị/xuất (xem compute_row_values)."""

    key: str
    label: str
    kind: str
    source_fields: list[str] = field(default_factory=list)
    separator: str = " "

    def normalized(self) -> "ComputedColumn":
        self.key = (self.key or "").strip() or f"computed_{abs(hash(self.label)) % 100000}"
        self.label = (self.label or "").strip() or self.key
        if self.kind not in COMPUTED_KINDS:
            self.kind = KIND_CONCAT
        self.source_fields = [f for f in (self.source_fields or []) if f in BASE_FIELD_LABELS]
        if self.kind == KIND_AGE:
            self.source_fields = ["birth_year"]
        elif self.kind == KIND_DAYS_BETWEEN:
            self.source_fields = [f for f in self.source_fields if f in DATE_LIKE_FIELDS][:2]
        self.separator = self.separator if isinstance(self.separator, str) else " "
        return self


@dataclass
class CaseViewConfig:
    """Cấu hình cột hiển thị cho danh sách ca bệnh (tab "Ca bệnh") — CDC tự chọn cột nào hiện,
    thứ tự, tiêu đề riêng, và các cột tính toán thêm. Lưu cục bộ theo máy (giống
    duplicate_config.py), không đồng bộ qua máy chủ vì đây là tuỳ chỉnh hiển thị cá nhân."""

    columns: list[tuple[str, str]] = field(default_factory=lambda: list(DEFAULT_COLUMNS))
    computed: list[ComputedColumn] = field(default_factory=list)

    def normalized(self) -> "CaseViewConfig":
        self.computed = [c.normalized() for c in self.computed]
        computed_keys = {c.key for c in self.computed}
        valid_keys = set(BASE_FIELD_LABELS) | computed_keys
        cleaned: list[tuple[str, str]] = []
        for key, label in self.columns or []:
            if key in valid_keys:
                cleaned.append((key, (label or "").strip() or self._default_label(key)))
        self.columns = cleaned or list(DEFAULT_COLUMNS)
        return self

    def _default_label(self, key: str) -> str:
        if key in BASE_FIELD_LABELS:
            return BASE_FIELD_LABELS[key]
        for c in self.computed:
            if c.key == key:
                return c.label
        return key


def default_config() -> CaseViewConfig:
    return CaseViewConfig()


def load_case_view_config() -> CaseViewConfig:
    if not CONFIG_PATH.exists():
        return default_config()
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_config()
    computed = [
        ComputedColumn(
            key=item.get("key", ""), label=item.get("label", ""), kind=item.get("kind", KIND_CONCAT),
            source_fields=item.get("source_fields") or [], separator=item.get("separator", " "),
        )
        for item in (raw.get("computed") or [])
    ]
    columns = [(item[0], item[1]) for item in (raw.get("columns") or []) if isinstance(item, list) and len(item) == 2]
    return CaseViewConfig(columns=columns or list(DEFAULT_COLUMNS), computed=computed).normalized()


def save_case_view_config(config: CaseViewConfig) -> Path:
    config.normalized()
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "columns": [list(pair) for pair in config.columns],
        "computed": [asdict(c) for c in config.computed],
    }
    temp = CONFIG_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(CONFIG_PATH)
    return CONFIG_PATH


def _parse_date_only(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text[:10]  # "YYYY-MM-DD" kể cả khi trường là datetime "YYYY-MM-DD HH:MM".
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def compute_row_values(row: dict[str, Any], computed_columns: list[ComputedColumn]) -> dict[str, Any]:
    """Tính giá trị các cột tính toán cho MỘT dòng dữ liệu — chạy lại mỗi lần hiển thị/xuất,
    không lưu vào CSDL, nên luôn phản ánh đúng dữ liệu gốc hiện tại."""
    result: dict[str, Any] = {}
    for column in computed_columns:
        try:
            if column.kind == KIND_AGE:
                birth_year = row.get("birth_year")
                result[column.key] = (datetime.now().year - int(birth_year)) if birth_year else ""
            elif column.kind == KIND_DAYS_BETWEEN and len(column.source_fields) == 2:
                start = _parse_date_only(row.get(column.source_fields[0]))
                end = _parse_date_only(row.get(column.source_fields[1]))
                result[column.key] = (end - start).days if start and end else ""
            elif column.kind == KIND_CONCAT:
                parts = [str(row.get(f, "")).strip() for f in column.source_fields]
                result[column.key] = column.separator.join(p for p in parts if p)
            else:
                result[column.key] = ""
        except (TypeError, ValueError):
            result[column.key] = ""
    return result
