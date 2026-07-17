from __future__ import annotations

import base64
import io
import json
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from openpyxl import Workbook

import core
import remote_core
from deployment_config import DeploymentConfig
from lan_server import LanServerController


def make_excel_bytes(fields, rows, sheet="Disease Cases") -> bytes:
    wb = Workbook(); ws = wb.active; ws.title = sheet
    ws.append([label for label, _ in fields])
    for values in rows:
        ws.append([values.get(key, "") for _, key in fields])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def post(addr: str, path: str, payload: dict, password: str | None = None) -> dict:
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if password is not None:
        headers["X-GSBTN-Password"] = password
    req = Request(addr + path, data=body, headers=headers, method="POST")
    try:
        return json.loads(urlopen(req, timeout=10).read().decode())
    except HTTPError as exc:
        return json.loads(exc.read().decode())


def test_create_verify_disable_commune_account():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp); db = root / "test.db"; core.BACKUP_DIR = root / "backups"
        assert core.has_commune_accounts(db_path=db) is False
        account = core.create_commune_account("Xã Gia Viên", "xagiavien", "matkhau123", db_path=db)
        assert core.has_commune_accounts(db_path=db) is True

        assert core.verify_commune_account("xagiavien", "sai_mat_khau", db_path=db) is None
        verified = core.verify_commune_account("XaGiaVien", "matkhau123", db_path=db)  # username không phân biệt hoa/thường
        assert verified["commune"] == "Xã Gia Viên"

        try:
            core.create_commune_account("Xã Gia Viên", "khac", "matkhau123", db_path=db)
            assert False, "phải báo lỗi khi xã đã có tài khoản"
        except ValueError:
            pass

        try:
            core.create_commune_account("Xã Khác", "xagiavien2", "ngan", db_path=db)
            assert False, "phải báo lỗi mật khẩu quá ngắn"
        except ValueError:
            pass

        core.set_commune_account_active(account["id"], False, db_path=db)
        assert core.verify_commune_account("xagiavien", "matkhau123", db_path=db) is None
        core.set_commune_account_active(account["id"], True, db_path=db)
        assert core.verify_commune_account("xagiavien", "matkhau123", db_path=db) is not None

        core.reset_commune_account_password(account["id"], "matkhaumoi123", db_path=db)
        assert core.verify_commune_account("xagiavien", "matkhau123", db_path=db) is None
        assert core.verify_commune_account("xagiavien", "matkhaumoi123", db_path=db) is not None


def test_commune_token_issue_verify_expiry_and_wrong_secret():
    token = core.issue_commune_token(1, "Xã Gia Viên", "xagiavien", "bi-mat-1", ttl_seconds=1)
    claims = core.verify_commune_token(token, "bi-mat-1")
    assert claims == {"account_id": 1, "commune": "Xã Gia Viên", "username": "xagiavien"}
    assert core.verify_commune_token(token, "sai-bi-mat") is None
    assert core.verify_commune_token("token-rac", "bi-mat-1") is None
    assert core.verify_commune_token("", "bi-mat-1") is None
    # Hạn dùng tính theo giây nguyên (int(time.time())) nên cần chờ dư hơn 1 giây làm tròn để
    # chắc chắn đã qua mốc hết hạn, tránh sai lệch do thời điểm bắt đầu nằm giữa giây.
    time.sleep(2.2)
    assert core.verify_commune_token(token, "bi-mat-1") is None


def test_audit_log_records_key_actions():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp); db = root / "test.db"
        core.BACKUP_DIR = root / "backups"; core.QUEUE_DIR = root / "queue"

        data = make_excel_bytes(core.CASE_FIELDS, [{"case_code": "CA-AUD1", "full_name": "Nguyễn Văn A"}])
        submitted = core.queue_submit("Xã Gia Viên", "2026-W29", "ds.xlsx", data, submitted_by="Cán bộ A", db_path=db)
        core.import_queue_item(submitted["queue_id"], db_path=db, actor="cdc_hoa")

        rows = [
            {"full_name": "Nguyễn Văn B", "case_code": "CA-DUP-1", "national_id": "111111111111", "commune": "Xã A"},
            {"full_name": "Nguyễn Văn B", "case_code": "CA-DUP-2", "national_id": "111111111111", "commune": "Xã A"},
        ]
        file2 = root / "dup.xlsx"
        wb = Workbook(); ws = wb.active; ws.title = "Disease Cases"
        ws.append([label for label, _ in core.CASE_FIELDS])
        for r in rows:
            ws.append([r.get(key, "") for _, key in core.CASE_FIELDS])
        wb.save(file2)
        core.import_excel(file2, db)
        groups = core.find_duplicate_groups("case", db_path=db)
        assert groups
        keep_id, remove_ids = groups[0]["record_ids"][0], groups[0]["record_ids"][1:]
        merge_result = core.merge_duplicate_records("case", keep_id, remove_ids, {}, db, actor="cdc_hoa")
        core.restore_duplicate_action(merge_result["action_id"], db_path=db, actor="cdc_hoa")

        core.archive_old_queue_files(90, db_path=db, actor="cdc_hoa")

        account = core.create_commune_account("Xã Đông Hải", "xadonghai", "matkhau123", db_path=db, actor="cdc_hoa")
        core.verify_commune_account("xadonghai", "sai", db_path=db)
        core.verify_commune_account("xadonghai", "matkhau123", db_path=db)
        core.set_commune_account_active(account["id"], False, db_path=db, actor="cdc_hoa")
        core.reset_commune_account_password(account["id"], "matkhaumoi123", db_path=db, actor="cdc_hoa")

        assert merge_result["merged_values"] == {}  # merged_values rỗng -> log dưới tên "remove_duplicate_records"
        actions = {item["action"] for item in core.list_audit_log(db_path=db)}
        expected = {
            "queue_submit", "import_queue_item", "remove_duplicate_records",
            "restore_duplicate_action", "archive_old_queue_files", "create_commune_account", "login",
            "login_failed", "disable_commune_account", "reset_commune_account_password",
        }
        missing = expected - actions
        assert not missing, f"thiếu hành động trong nhật ký: {missing}; đã có: {actions}"

        commune_filtered = core.list_audit_log(db_path=db, commune="Xã Gia Viên")
        assert all(item["commune"] == "Xã Gia Viên" for item in commune_filtered)
        assert any(item["action"] == "queue_submit" for item in commune_filtered)


def test_queue_submit_accepts_token_or_shared_password_side_by_side():
    """/queue/submit phải chấp nhận song song 2 đường xác thực (không loại trừ nhau):
    token đăng nhập xã (dùng bởi trang /xa) và mật khẩu máy chủ dùng chung (dùng bởi máy trạm
    nội bộ và bởi Google Apps Script khi chuyển tiếp trực tiếp — GAS không có token riêng
    từng xã). Việc đã có tài khoản xã không được làm mất đường mật khẩu dùng chung."""
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
            data = make_excel_bytes(core.CASE_FIELDS, [{"case_code": "CA-1"}])
            legacy = post(addr, "/queue/submit", {
                "commune": "Xã Legacy", "week": "2026-W29", "file_name": "ds.xlsx",
                "content_base64": base64.b64encode(data).decode("ascii"),
            }, password="matkhauchung")
            assert legacy["ok"] and legacy["result"]["commune"] == "Xã Legacy"

            core.create_commune_account("Xã Gia Viên", "xagiavien", "matkhau123", db_path=core.DB_PATH)

            # Không token, không mật khẩu đúng -> bị chặn.
            no_auth = post(addr, "/queue/submit", {
                "commune": "Xã Bất Kỳ", "week": "2026-W29", "file_name": "ds2.xlsx",
                "content_base64": base64.b64encode(data).decode("ascii"),
            })
            assert no_auth["ok"] is False

            # Không token nhưng đúng mật khẩu dùng chung (mô phỏng GAS chuyển tiếp trực tiếp)
            # -> vẫn nộp được dù hệ thống đã có tài khoản xã.
            via_shared_password = post(addr, "/queue/submit", {
                "commune": "Xã Đông Hải", "week": "2026-W29", "file_name": "ds2.xlsx",
                "content_base64": base64.b64encode(data).decode("ascii"),
            }, password="matkhauchung")
            assert via_shared_password["ok"] and via_shared_password["result"]["commune"] == "Xã Đông Hải"

            bad_login = post(addr, "/xa/login", {"username": "xagiavien", "password": "sai"})
            assert bad_login["ok"] is False

            login = post(addr, "/xa/login", {"username": "xagiavien", "password": "matkhau123"})
            assert login["ok"]
            token = login["result"]["token"]

            # Có token hợp lệ -> nộp được dù KHÔNG gửi mật khẩu, và commune lấy theo token
            # (bỏ qua "Xã Giả Mạo" tự khai trên payload).
            submitted = post(addr, "/queue/submit", {
                "commune": "Xã Giả Mạo", "week": "2026-W30", "file_name": "ds3.xlsx", "commune_token": token,
                "content_base64": base64.b64encode(data).decode("ascii"),
            })
            assert submitted["ok"] and submitted["result"]["commune"] == "Xã Gia Viên"

            with_bad_token = post(addr, "/queue/submit", {
                "commune": "Xã X", "week": "2026-W30", "file_name": "ds4.xlsx", "commune_token": "token-gia-mao",
                "content_base64": base64.b64encode(data).decode("ascii"),
            })
            assert with_bad_token["ok"] is False
        finally:
            ctrl.stop()


def test_queue_submit_rate_limit_keyed_by_commune_not_only_ip():
    """Nhiều xã cùng đi qua một IP (giả lập GAS chuyển tiếp) không được dùng chung 1 hạn mức —
    xã A gửi dồn dập không được chặn oan xã B chỉ vì cùng nguồn IP."""
    import lan_server as lan_server_module

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        core.DATA_DIR = root / "data"; core.DATA_DIR.mkdir()
        core.DB_PATH = core.DATA_DIR / "test.db"
        core.BACKUP_DIR = root / "backups"; core.QUEUE_DIR = root / "queue"
        original_limit = lan_server_module.QUEUE_SUBMIT_RATE_LIMIT
        lan_server_module.QUEUE_SUBMIT_RATE_LIMIT = 2
        cfg = DeploymentConfig(mode="server", server_host="127.0.0.1", server_port=0, password="")
        ctrl = LanServerController(cfg)
        ctrl.start()
        addr = f"http://127.0.0.1:{ctrl.port}"
        try:
            data = make_excel_bytes(core.CASE_FIELDS, [{"case_code": "CA-1"}])

            def submit(commune: str) -> dict:
                return post(addr, "/queue/submit", {
                    "commune": commune, "week": "2026-W29", "file_name": "ds.xlsx",
                    "content_base64": base64.b64encode(data).decode("ascii"),
                })

            assert submit("Xã A")["ok"]
            assert submit("Xã A")["ok"]
            assert submit("Xã A")["ok"] is False  # Xã A đã chạm hạn mức riêng của mình.

            # Xã B (cùng IP localhost trong test) vẫn nộp được vì có hạn mức riêng theo (IP, xã).
            assert submit("Xã B")["ok"]
        finally:
            ctrl.stop()
            lan_server_module.QUEUE_SUBMIT_RATE_LIMIT = original_limit


def test_remote_core_account_and_audit_proxies(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        core.DATA_DIR = root / "data"; core.DATA_DIR.mkdir()
        core.DB_PATH = core.DATA_DIR / "test.db"
        core.BACKUP_DIR = root / "backups"; core.QUEUE_DIR = root / "queue"
        cfg = DeploymentConfig(mode="server", server_host="127.0.0.1", server_port=0, password="")
        ctrl = LanServerController(cfg)
        ctrl.start()
        try:
            workstation_cfg = DeploymentConfig(mode="workstation", server_url=f"http://127.0.0.1:{ctrl.port}")
            monkeypatch.setattr(remote_core, "load_config", lambda: workstation_cfg)

            created = remote_core.create_commune_account("Xã Gia Viên", "xagiavien", "matkhau123", actor="tester")
            assert created["commune"] == "Xã Gia Viên"

            accounts = remote_core.list_commune_accounts()
            assert len(accounts) == 1 and accounts[0]["username"] == "xagiavien"

            remote_core.set_commune_account_active(accounts[0]["id"], False, actor="tester")
            remote_core.reset_commune_account_password(accounts[0]["id"], "matkhaumoi123", actor="tester")

            logs = remote_core.list_audit_log(limit=50)
            actions = {item["action"] for item in logs}
            assert {"create_commune_account", "disable_commune_account", "reset_commune_account_password"} <= actions
        finally:
            ctrl.stop()
