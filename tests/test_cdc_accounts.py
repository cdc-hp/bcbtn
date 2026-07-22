from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import core
import remote_core
from deployment_config import DeploymentConfig
from lan_server import LanServerController


def post(addr: str, path: str, payload: dict, password: str | None = None, admin_token: str | None = None) -> dict:
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if password is not None:
        headers["X-GSBTN-Password"] = password
    if admin_token is not None:
        headers["X-GSBTN-Admin-Token"] = admin_token
    req = Request(addr + path, data=body, headers=headers, method="POST")
    try:
        return json.loads(urlopen(req, timeout=10).read().decode())
    except HTTPError as exc:
        return json.loads(exc.read().decode())


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


def test_cdc_login_and_rpc_actor_prefers_admin_identity_over_ip():
    """Sau khi đăng nhập /cdc/login, các lời gọi /rpc dùng X-GSBTN-Admin-Token phải ghi nhật ký
    kiểm toán theo tên đăng nhập quản trị viên thay vì "LAN:<ip>" — đồng thời mật khẩu máy chủ
    dùng chung vẫn phải tiếp tục hoạt động song song (không loại trừ nhau, như /queue/submit)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        core.DATA_DIR = root / "data"; core.DATA_DIR.mkdir()
        core.DB_PATH = core.DATA_DIR / "test.db"
        core.BACKUP_DIR = root / "backups"; core.QUEUE_DIR = root / "queue"
        cfg = DeploymentConfig(mode="server", server_host="127.0.0.1", server_port=0, password="matkhauchung")
        ctrl = LanServerController(cfg)
        ctrl.start()
        addr = f"http://127.0.0.1:{ctrl.port}"
        try:
            core.create_cdc_account("cdc_hoa", "matkhau123", "Nguyễn Thị Hoa", db_path=core.DB_PATH)

            bad_login = post(addr, "/cdc/login", {"username": "cdc_hoa", "password": "sai"})
            assert bad_login["ok"] is False

            login = post(addr, "/cdc/login", {"username": "cdc_hoa", "password": "matkhau123"})
            assert login["ok"]
            token = login["result"]["token"]
            assert login["result"]["display_name"] == "Nguyễn Thị Hoa"

            # Gọi /rpc bằng admin token (không kèm mật khẩu dùng chung) -> vẫn được phép, và
            # actor trong nhật ký kiểm toán ghi theo tên đăng nhập, không phải "LAN:127.0.0.1".
            result = post(addr, "/rpc", {"function": "archive_old_queue_files", "args": [90], "kwargs": {}}, admin_token=token)
            assert result["ok"], result

            # Mật khẩu dùng chung vẫn hoạt động song song, không bị token "thế chỗ".
            result2 = post(addr, "/rpc", {"function": "archive_old_queue_files", "args": [90], "kwargs": {}}, password="matkhauchung")
            assert result2["ok"], result2

            # Không token, không đúng mật khẩu -> bị chặn.
            result3 = post(addr, "/rpc", {"function": "archive_old_queue_files", "args": [90], "kwargs": {}})
            assert result3["ok"] is False

            actions = core.list_audit_log(db_path=core.DB_PATH, action="archive_old_queue_files")
            actors = {item["actor"] for item in actions}
            assert "cdc_hoa" in actors, f"actor phải là tên quản trị viên khi dùng token, đã có: {actors}"
            assert any(a.startswith("LAN:") for a in actors), f"actor phải trở lại IP khi dùng mật khẩu dùng chung, đã có: {actors}"
        finally:
            ctrl.stop()


def test_remote_core_login_stores_token_and_included_in_subsequent_requests(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        core.DATA_DIR = root / "data"; core.DATA_DIR.mkdir()
        core.DB_PATH = core.DATA_DIR / "test.db"
        core.BACKUP_DIR = root / "backups"; core.QUEUE_DIR = root / "queue"
        cfg = DeploymentConfig(mode="server", server_host="127.0.0.1", server_port=0, password="")
        ctrl = LanServerController(cfg)
        ctrl.start()
        try:
            core.create_cdc_account("cdc_hoa", "matkhau123", "Nguyễn Thị Hoa", db_path=core.DB_PATH)

            holder = {"config": DeploymentConfig(mode="workstation", server_url=f"http://127.0.0.1:{ctrl.port}")}
            monkeypatch.setattr(remote_core, "load_config", lambda: holder["config"])

            def fake_save(config):
                holder["config"] = config
                return Path("unused")

            monkeypatch.setattr(remote_core, "save_config", fake_save)

            assert remote_core.current_admin_username() == ""
            result = remote_core.login("cdc_hoa", "matkhau123")
            assert result["username"] == "cdc_hoa"
            assert holder["config"].admin_token
            assert remote_core.current_admin_username() == "cdc_hoa"

            # Lời gọi RPC tiếp theo phải tự gửi kèm token đã lưu và ghi actor đúng tên đăng nhập.
            remote_core.archive_old_queue_files(90, actor="")
            actions = core.list_audit_log(db_path=core.DB_PATH, action="archive_old_queue_files")
            assert any(item["actor"] == "cdc_hoa" for item in actions)

            remote_core.logout()
            assert holder["config"].admin_token == ""
            assert remote_core.current_admin_username() == ""
        finally:
            ctrl.stop()
