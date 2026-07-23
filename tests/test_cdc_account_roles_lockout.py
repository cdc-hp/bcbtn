"""Vai trò, khoá tài khoản sau nhiều lần đăng nhập sai, và bắt buộc đổi mật khẩu — phần nền
tảng cho Web App tập trung (xem TASKS.md mục 5 và CLAUDE.md mục "Đăng nhập và phân quyền")."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import core


def _fresh_db(tmp: str) -> Path:
    root = Path(tmp)
    core.BACKUP_DIR = root / "backups"
    return root / "test.db"


def test_create_cdc_account_default_role_and_forced_change():
    with tempfile.TemporaryDirectory() as tmp:
        db = _fresh_db(tmp)
        account = core.create_cdc_account("cdc_an", "matkhau123", "Trần Văn An", db_path=db)
        assert account["role"] == core.CDC_ROLE_ADMIN
        rows = core.list_cdc_accounts(db_path=db)
        assert rows[0]["role"] == core.CDC_ROLE_ADMIN
        assert rows[0]["must_change_password"] == 1


def test_create_cdc_account_rejects_invalid_role():
    with tempfile.TemporaryDirectory() as tmp:
        db = _fresh_db(tmp)
        with pytest.raises(ValueError):
            core.create_cdc_account("cdc_an", "matkhau123", role="giam_doc", db_path=db)


def test_verify_cdc_account_reports_role_and_must_change_password():
    with tempfile.TemporaryDirectory() as tmp:
        db = _fresh_db(tmp)
        core.create_cdc_account(
            "cdc_super", "matkhau123", role=core.CDC_ROLE_SUPER_ADMIN, must_change_password=False, db_path=db,
        )
        result = core.verify_cdc_account("cdc_super", "matkhau123", db_path=db)
        assert result["role"] == core.CDC_ROLE_SUPER_ADMIN
        assert result["must_change_password"] is False


def test_account_locks_after_threshold_failed_attempts():
    with tempfile.TemporaryDirectory() as tmp:
        db = _fresh_db(tmp)
        core.create_cdc_account("cdc_binh", "matkhau123", db_path=db)

        for _ in range(core.ACCOUNT_LOCKOUT_THRESHOLD - 1):
            assert core.verify_cdc_account("cdc_binh", "sai", db_path=db) is None
        assert core.get_cdc_account_lock_status("cdc_binh", db_path=db) is None  # chưa đủ ngưỡng

        # Lần sai cuối cùng chạm ngưỡng -> khoá.
        assert core.verify_cdc_account("cdc_binh", "sai", db_path=db) is None
        status = core.get_cdc_account_lock_status("cdc_binh", db_path=db)
        assert status is not None and status["locked_until"]

        # Đúng mật khẩu vẫn bị chặn vì đang khoá.
        assert core.verify_cdc_account("cdc_binh", "matkhau123", db_path=db) is None


def test_successful_login_resets_failed_count():
    with tempfile.TemporaryDirectory() as tmp:
        db = _fresh_db(tmp)
        core.create_cdc_account("cdc_chi", "matkhau123", db_path=db)
        core.verify_cdc_account("cdc_chi", "sai", db_path=db)
        core.verify_cdc_account("cdc_chi", "sai", db_path=db)
        assert core.verify_cdc_account("cdc_chi", "matkhau123", db_path=db) is not None
        rows = core.list_cdc_accounts(db_path=db)
        assert rows[0]["failed_login_count"] == 0
        assert rows[0]["locked_until"] is None


def test_reset_password_forces_change_and_unlocks():
    with tempfile.TemporaryDirectory() as tmp:
        db = _fresh_db(tmp)
        account = core.create_cdc_account("cdc_dung", "matkhau123", must_change_password=False, db_path=db)
        for _ in range(core.ACCOUNT_LOCKOUT_THRESHOLD):
            core.verify_cdc_account("cdc_dung", "sai", db_path=db)
        assert core.get_cdc_account_lock_status("cdc_dung", db_path=db) is not None

        core.reset_cdc_account_password(account["id"], "matkhaumoi123", db_path=db)
        assert core.get_cdc_account_lock_status("cdc_dung", db_path=db) is None
        result = core.verify_cdc_account("cdc_dung", "matkhaumoi123", db_path=db)
        assert result["must_change_password"] is True


def test_change_password_requires_correct_current_password():
    with tempfile.TemporaryDirectory() as tmp:
        db = _fresh_db(tmp)
        account = core.create_cdc_account("cdc_em", "matkhau123", db_path=db)
        with pytest.raises(ValueError):
            core.change_cdc_account_password(account["id"], "sai", "matkhaumoi123", db_path=db)
        core.change_cdc_account_password(account["id"], "matkhau123", "matkhaumoi123", db_path=db)
        result = core.verify_cdc_account("cdc_em", "matkhaumoi123", db_path=db)
        assert result["must_change_password"] is False


def test_set_cdc_account_role_validates_and_updates():
    with tempfile.TemporaryDirectory() as tmp:
        db = _fresh_db(tmp)
        account = core.create_cdc_account("cdc_giang", "matkhau123", db_path=db)
        with pytest.raises(ValueError):
            core.set_cdc_account_role(account["id"], "khong_hop_le", db_path=db)
        core.set_cdc_account_role(account["id"], core.CDC_ROLE_VIEWER, db_path=db)
        rows = core.list_cdc_accounts(db_path=db)
        assert rows[0]["role"] == core.CDC_ROLE_VIEWER


def test_disable_account_clears_lockout():
    with tempfile.TemporaryDirectory() as tmp:
        db = _fresh_db(tmp)
        account = core.create_cdc_account("cdc_hoang", "matkhau123", db_path=db)
        for _ in range(core.ACCOUNT_LOCKOUT_THRESHOLD):
            core.verify_cdc_account("cdc_hoang", "sai", db_path=db)
        core.set_cdc_account_active(account["id"], False, db_path=db)
        rows = core.list_cdc_accounts(db_path=db)
        assert rows[0]["active"] == 0
        assert rows[0]["locked_until"] is None
