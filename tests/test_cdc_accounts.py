from __future__ import annotations

import tempfile
import time
from pathlib import Path

import core


def test_create_verify_disable_cdc_account():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp); db = root / "test.db"; core.BACKUP_DIR = root / "backups"
        assert core.has_cdc_accounts(db_path=db) is False
        account = core.create_cdc_account("cdc_hoa", "matkhau123", "Nguyễn Thị Hoa", db_path=db)
        assert core.has_cdc_accounts(db_path=db) is True

        assert core.verify_cdc_account("cdc_hoa", "sai_mat_khau", db_path=db) is None
        verified = core.verify_cdc_account("CDC_Hoa", "matkhau123", db_path=db)  # không phân biệt hoa/thường
        assert verified["display_name"] == "Nguyễn Thị Hoa"

        try:
            core.create_cdc_account("cdc_hoa", "matkhau456", db_path=db)
            assert False, "phải báo lỗi khi tên đăng nhập đã tồn tại"
        except ValueError:
            pass

        try:
            core.create_cdc_account("cdc_lan", "ngan", db_path=db)
            assert False, "phải báo lỗi mật khẩu quá ngắn"
        except ValueError:
            pass

        core.set_cdc_account_active(account["id"], False, db_path=db)
        assert core.verify_cdc_account("cdc_hoa", "matkhau123", db_path=db) is None
        core.set_cdc_account_active(account["id"], True, db_path=db)
        assert core.verify_cdc_account("cdc_hoa", "matkhau123", db_path=db) is not None

        core.reset_cdc_account_password(account["id"], "matkhaumoi123", db_path=db)
        assert core.verify_cdc_account("cdc_hoa", "matkhau123", db_path=db) is None
        assert core.verify_cdc_account("cdc_hoa", "matkhaumoi123", db_path=db) is not None


def test_admin_token_issue_verify_expiry_and_wrong_secret():
    token = core.issue_admin_token(1, "cdc_hoa", "bi-mat-1", ttl_seconds=1)
    claims = core.verify_admin_token(token, "bi-mat-1")
    assert claims == {"account_id": 1, "username": "cdc_hoa"}
    assert core.verify_admin_token(token, "sai-bi-mat") is None
    assert core.verify_admin_token("token-rac", "bi-mat-1") is None
    assert core.verify_admin_token("", "bi-mat-1") is None
    time.sleep(2.2)
    assert core.verify_admin_token(token, "bi-mat-1") is None
