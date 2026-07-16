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

DEFAULT_CASE_WEIGHTS = {
    "name": 35,
    "phone": 35,
    "birth_year": 15,
    "gender": 5,
    "area": 8,
    "disease": 7,
    "onset_exact": 15,
    "onset_near": 10,
    "address": 5,
}
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
    min_score: int = 65
    definite_score: int = 85
    case_weights: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_CASE_WEIGHTS))
    outbreak_weights: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_OUTBREAK_WEIGHTS))

    def normalized(self) -> "DuplicateRules":
        self.min_score = max(40, min(100, int(self.min_score)))
        self.definite_score = max(self.min_score, min(100, int(self.definite_score)))
        self.case_weights = _normalized_weights(self.case_weights, DEFAULT_CASE_WEIGHTS)
        self.outbreak_weights = _normalized_weights(self.outbreak_weights, DEFAULT_OUTBREAK_WEIGHTS)
        return self

    def weights_for(self, entity_type: str) -> dict[str, int]:
        return dict(self.case_weights if entity_type == "case" else self.outbreak_weights)


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
        case_weights=raw.get("case_weights") or dict(DEFAULT_CASE_WEIGHTS),
        outbreak_weights=raw.get("outbreak_weights") or dict(DEFAULT_OUTBREAK_WEIGHTS),
    ).normalized()


def save_rules(rules: DuplicateRules) -> Path:
    rules.normalized()
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = CONFIG_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(asdict(rules), ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(CONFIG_PATH)
    return CONFIG_PATH
