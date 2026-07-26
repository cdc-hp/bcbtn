from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def _user_data_root() -> Path:
    override = os.environ.get("GIAM_SAT_DICH_BENH_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "CDC_HaiPhong" / "GiamSatDichBenh"
    return Path.home() / ".giam_sat_dich_benh"


CONFIG_PATH = _user_data_root() / "duplicate_rules.json"

LEGACY_CASE_CRITERIA_DEFS: list[tuple[str, str]] = [
    ("case_code", "Trùng mã ca bệnh"),
    ("national_id", "Trùng CCCD/CMND"),
    ("phone", "Trùng số điện thoại"),
    ("name_birth_year", "Trùng họ tên + năm sinh"),
    ("name_commune", "Trùng họ tên + xã/phường"),
    ("name_similar", "Họ tên gần giống"),
    ("onset_near", "Ngày khởi phát gần nhau"),
]
CASE_CRITERIA_DEFS = LEGACY_CASE_CRITERIA_DEFS  # Tương thích import của các bản cũ.
CASE_CRITERIA_LABELS: dict[str, str] = dict(LEGACY_CASE_CRITERIA_DEFS)
LEGACY_CRITERIA_FIELD_MAP: dict[str, list[str]] = {
    "case_code": ["case_code"],
    "national_id": ["national_id"],
    "phone": ["phone"],
    "name_birth_year": ["full_name", "birth_date_raw"],
    "name_commune": ["full_name", "commune"],
    "name_similar": ["full_name"],
    "onset_near": ["onset_date"],
}
DEFAULT_CASE_CRITERIA = ["case_code"]

CRITERIA_CONFIG_PATH = _user_data_root() / "case_duplicate_criteria.json"


@dataclass
class CaseDuplicateCriteria:
    """Các trường dữ liệu dùng làm khóa lọc trùng ca bệnh.

    ``name_similarity_percent`` và ``onset_max_days`` chỉ được giữ để đọc tệp cấu hình của
    phiên bản cũ; cơ chế mới so khớp chính xác toàn bộ trường trong ``enabled``.
    """

    enabled: list[str] = field(default_factory=lambda: list(DEFAULT_CASE_CRITERIA))
    match_mode: str = "fields"
    name_similarity_percent: int = 92
    onset_max_days: int = 3

    def normalized(self, valid_fields: set[str] | None = None) -> "CaseDuplicateCriteria":
        expanded: list[str] = []
        for value in self.enabled or []:
            for field_name in LEGACY_CRITERIA_FIELD_MAP.get(str(value), [str(value)]):
                if field_name not in expanded:
                    expanded.append(field_name)
        valid = valid_fields or {value for value in expanded if value.replace("_", "").isalnum()}
        seen: list[str] = []
        for field_name in expanded:
            if field_name in valid and field_name not in seen:
                seen.append(field_name)
        self.enabled = seen or list(DEFAULT_CASE_CRITERIA)
        self.match_mode = "fields"
        self.name_similarity_percent = max(50, min(100, int(self.name_similarity_percent)))
        self.onset_max_days = max(0, min(60, int(self.onset_max_days)))
        return self


def load_case_criteria() -> CaseDuplicateCriteria:
    if not CRITERIA_CONFIG_PATH.exists():
        return CaseDuplicateCriteria()
    try:
        raw = json.loads(CRITERIA_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return CaseDuplicateCriteria()
    return CaseDuplicateCriteria(
        enabled=raw.get("enabled") or list(DEFAULT_CASE_CRITERIA),
        match_mode=raw.get("match_mode", "fields"),
        name_similarity_percent=raw.get("name_similarity_percent", 92),
        onset_max_days=raw.get("onset_max_days", 3),
    ).normalized()


def save_case_criteria(criteria: CaseDuplicateCriteria) -> Path:
    criteria.normalized()
    CRITERIA_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = CRITERIA_CONFIG_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(asdict(criteria), ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(CRITERIA_CONFIG_PATH)
    return CRITERIA_CONFIG_PATH


DEFAULT_OUTBREAK_WEIGHTS = {
    "disease": 30,
    "location_exact": 45,
    "location_near": 35,
    "area": 10,
    "onset_exact": 20,
    "onset_near": 15,
    "reporting_unit": 5,
}


@dataclass
class DuplicateRules:
    """Ngưỡng/trọng số lọc trùng ổ dịch. Ca bệnh dùng CaseDuplicateCriteria (chọn tiêu chí)."""

    min_score: int = 65
    definite_score: int = 85
    outbreak_weights: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_OUTBREAK_WEIGHTS))

    def normalized(self) -> "DuplicateRules":
        self.min_score = max(40, min(100, int(self.min_score)))
        self.definite_score = max(self.min_score, min(100, int(self.definite_score)))
        self.outbreak_weights = _normalized_weights(self.outbreak_weights, DEFAULT_OUTBREAK_WEIGHTS)
        return self

    def weights_for(self, entity_type: str) -> dict[str, int]:
        return dict(self.outbreak_weights)


def _normalized_weights(values: dict[str, Any] | None, defaults: dict[str, int]) -> dict[str, int]:
    values = values or {}
    result: dict[str, int] = {}
    for key, default in defaults.items():
        try:
            result[key] = max(0, min(100, int(values.get(key, default))))
        except (TypeError, ValueError):
            result[key] = default
    return result


def load_rules() -> DuplicateRules:
    if not CONFIG_PATH.exists():
        return DuplicateRules()
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DuplicateRules()
    return DuplicateRules(
        min_score=raw.get("min_score", 65),
        definite_score=raw.get("definite_score", 85),
        outbreak_weights=raw.get("outbreak_weights") or dict(DEFAULT_OUTBREAK_WEIGHTS),
    ).normalized()


def save_rules(rules: DuplicateRules) -> Path:
    rules.normalized()
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = CONFIG_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(asdict(rules), ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(CONFIG_PATH)
    return CONFIG_PATH
