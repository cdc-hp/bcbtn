from __future__ import annotations

import tempfile
from pathlib import Path

import case_view_config as cvc


def test_default_config_matches_hardcoded_columns():
    cfg = cvc.default_config()
    assert cfg.columns == cvc.DEFAULT_COLUMNS
    assert cfg.computed == []


def test_save_and_load_round_trip(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr(cvc, "CONFIG_PATH", Path(tmp) / "case_view_config.json")
        cfg = cvc.CaseViewConfig(
            columns=[("case_code", "Mã số"), ("tuoi", "Tuổi")],
            computed=[cvc.ComputedColumn(key="tuoi", label="Tuổi", kind=cvc.KIND_AGE)],
        )
        cvc.save_case_view_config(cfg)
        loaded = cvc.load_case_view_config()
        assert loaded.columns == [("case_code", "Mã số"), ("tuoi", "Tuổi")]
        assert len(loaded.computed) == 1
        assert loaded.computed[0].key == "tuoi"
        assert loaded.computed[0].source_fields == ["birth_year"]  # age luôn tự gán birth_year


def test_load_missing_file_returns_default(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr(cvc, "CONFIG_PATH", Path(tmp) / "khong_ton_tai.json")
        loaded = cvc.load_case_view_config()
        assert loaded.columns == cvc.DEFAULT_COLUMNS


def test_normalized_drops_unknown_field_and_computed_referencing_missing_source():
    cfg = cvc.CaseViewConfig(
        columns=[("case_code", ""), ("truong_khong_ton_tai", "Lạ"), ("do_dai", "")],
        computed=[cvc.ComputedColumn(key="do_dai", label="", kind=cvc.KIND_CONCAT, source_fields=["full_name", "khong_hop_le"])],
    )
    cfg.normalized()
    keys = [k for k, _ in cfg.columns]
    assert "truong_khong_ton_tai" not in keys
    assert "case_code" in keys and "do_dai" in keys
    assert cfg.columns[0] == ("case_code", "Mã số")  # nhãn rỗng -> tự điền nhãn mặc định
    assert cfg.computed[0].source_fields == ["full_name"]  # bỏ trường nguồn không hợp lệ


def test_days_between_only_accepts_date_like_fields():
    column = cvc.ComputedColumn(
        key="k", label="K", kind=cvc.KIND_DAYS_BETWEEN,
        source_fields=["onset_date", "full_name", "admission_date"],
    )
    column.normalized()
    assert column.source_fields == ["onset_date", "admission_date"]  # full_name bị loại, giữ tối đa 2


def test_compute_row_values_age_days_between_concat():
    computed = [
        cvc.ComputedColumn(key="tuoi", label="Tuổi", kind=cvc.KIND_AGE, source_fields=["birth_year"]),
        cvc.ComputedColumn(key="so_ngay", label="Số ngày", kind=cvc.KIND_DAYS_BETWEEN, source_fields=["onset_date", "admission_date"]),
        cvc.ComputedColumn(key="ten_xa", label="Họ tên + Xã", kind=cvc.KIND_CONCAT, source_fields=["full_name", "commune"], separator=" - "),
    ]
    row = {
        "birth_year": 1990, "onset_date": "2026-01-01", "admission_date": "2026-01-05",
        "full_name": "Nguyễn Văn A", "commune": "Xã Gia Viên",
    }
    import datetime as dt
    result = cvc.compute_row_values(row, computed)
    assert result["tuoi"] == dt.datetime.now().year - 1990
    assert result["so_ngay"] == 4
    assert result["ten_xa"] == "Nguyễn Văn A - Xã Gia Viên"


def test_compute_row_values_missing_data_returns_empty_string_not_error():
    computed = [
        cvc.ComputedColumn(key="tuoi", label="Tuổi", kind=cvc.KIND_AGE, source_fields=["birth_year"]),
        cvc.ComputedColumn(key="so_ngay", label="Số ngày", kind=cvc.KIND_DAYS_BETWEEN, source_fields=["onset_date", "admission_date"]),
    ]
    result = cvc.compute_row_values({}, computed)
    assert result == {"tuoi": "", "so_ngay": ""}


def test_available_base_fields_include_all_case_fields_plus_birth_year():
    import core
    case_db_fields = {db for _, db in core.CASE_FIELDS}
    available = {db for _, db in cvc.AVAILABLE_BASE_FIELDS}
    assert case_db_fields <= available
    assert "birth_year" in available
    assert cvc.BASE_FIELD_LABELS["birth_year"] == "Năm sinh"
