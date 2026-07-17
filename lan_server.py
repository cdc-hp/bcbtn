from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
from collections import deque
from dataclasses import asdict, is_dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import core
import secondary_sync
from deployment_config import DeploymentConfig, ensure_web_token_secret, load_config
from lan_discovery import DiscoveryResponder, get_lan_ip

MAX_REQUEST_BYTES = 110 * 1024 * 1024
QUEUE_SUBMIT_RATE_LIMIT = 10
QUEUE_SUBMIT_RATE_WINDOW_SECONDS = 300
READ_FUNCTIONS = {
    "dashboard_stats", "disease_summary", "monthly_outbreak_summary", "recent_active_outbreaks",
    "list_filter_values", "query_records", "get_record", "list_quality_issues",
    "list_import_batches", "execute_select", "find_duplicate_groups", "list_duplicate_actions",
    "list_backups", "list_import_queue", "list_commune_accounts", "list_audit_log",
}
WRITE_FUNCTIONS = {
    "save_outbreak", "delete_record", "remove_duplicate_records", "merge_duplicate_records",
    "restore_duplicate_action", "create_backup", "import_queue_item", "archive_old_queue_files",
    "create_commune_account", "set_commune_account_active", "reset_commune_account_password",
}
# Các hàm ghi có tham số actor — máy chủ tự điền actor mặc định theo IP nếu người gọi chưa cung cấp,
# để nhật ký kiểm toán luôn có "ai" thực hiện ngay cả khi gọi qua Máy trạm.
AUDITED_FUNCTIONS = {
    "remove_duplicate_records", "merge_duplicate_records", "restore_duplicate_action",
    "import_queue_item", "archive_old_queue_files", "create_commune_account",
    "set_commune_account_active", "reset_commune_account_password",
}

DB_FUNCTIONS = {
    "dashboard_stats", "disease_summary", "monthly_outbreak_summary", "recent_active_outbreaks",
    "list_filter_values", "query_records", "get_record", "save_outbreak", "delete_record",
    "list_quality_issues", "list_import_batches", "execute_select", "find_duplicate_groups",
    "remove_duplicate_records", "merge_duplicate_records", "list_duplicate_actions",
    "restore_duplicate_action", "create_backup", "list_import_queue", "import_queue_item",
    "archive_old_queue_files", "list_commune_accounts", "list_audit_log",
    "create_commune_account", "set_commune_account_active", "reset_commune_account_password",
}


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def port_available(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, int(port)))
        return True
    except OSError:
        return False
    finally:
        sock.close()


PUBLIC_HTML_PAGES = {"/xa", "/cdc/hang-doi"}

XA_UPLOAD_PAGE_HTML = """<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nộp danh sách ca bệnh — Trạm Y tế xã</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 560px; margin: 24px auto; padding: 0 16px; color: #1f2937; }
  h1 { font-size: 1.25rem; }
  label { display: block; margin-top: 12px; font-weight: 600; }
  input { width: 100%; padding: 8px; margin-top: 4px; box-sizing: border-box; border: 1px solid #cbd5e1; border-radius: 6px; }
  button { margin-top: 18px; padding: 10px 16px; background: #2563eb; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-size: 1rem; }
  button:disabled { background: #94a3b8; }
  #msg, #login-msg { margin-top: 16px; padding: 10px; border-radius: 6px; display: none; }
  #msg.ok, #login-msg.ok { background: #dcfce7; color: #166534; display: block; }
  #msg.err, #login-msg.err { background: #fee2e2; color: #991b1b; display: block; }
  #banner { margin-top: 16px; padding: 10px; border-radius: 6px; background: #eef2ff; color: #3730a3; display: none; }
  a.link { color: #2563eb; cursor: pointer; font-size: 0.9rem; display: inline-block; margin-top: 12px; }
  #submit-section, #legacy-fields { display: none; }
</style>
</head>
<body>
<h1>Nộp danh sách ca bệnh hằng tuần</h1>
<p>Nếu không kết nối được máy chủ chính, hãy dùng đường dẫn máy chủ phụ do CDC cung cấp.</p>

<div id="login-section">
  <form id="login-form">
    <label>Tên đăng nhập tài khoản xã</label>
    <input name="username" id="login-username" autocomplete="username">
    <label>Mật khẩu</label>
    <input name="password" type="password" id="login-password" autocomplete="current-password">
    <button type="submit">Đăng nhập</button>
  </form>
  <div id="login-msg"></div>
  <a class="link" id="legacy-toggle">Chưa có tài khoản xã? Nộp bằng mật khẩu máy chủ dùng chung (chế độ cũ)</a>
</div>

<div id="banner"></div>

<div id="submit-section">
  <form id="f">
    <div id="legacy-fields">
      <label>Xã / phường</label>
      <input name="commune" placeholder="Ví dụ: Xã Gia Viên">
      <label>Mật khẩu máy chủ (nếu có)</label>
      <input name="password" type="password" placeholder="Để trống nếu máy chủ không đặt mật khẩu">
    </div>
    <label>Tuần báo cáo</label>
    <input name="week" required placeholder="Ví dụ: 2026-W29" id="week">
    <label>Người nộp</label>
    <input name="submitted_by" placeholder="Họ tên cán bộ nộp (không bắt buộc)">
    <label>File Excel (.xlsx)</label>
    <input name="file" type="file" accept=".xlsx,.xlsm" required>
    <button type="submit">Nộp vào hàng đợi</button>
  </form>
  <div id="msg"></div>
</div>

<script>
function isoWeek(d) {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const day = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - day + 3);
  const firstThursday = new Date(Date.UTC(date.getUTCFullYear(), 0, 4));
  const week = 1 + Math.round(((date - firstThursday) / 86400000 - 3 + ((firstThursday.getUTCDay() + 6) % 7)) / 7);
  return date.getUTCFullYear() + "-W" + String(week).padStart(2, "0");
}
document.getElementById("week").value = isoWeek(new Date());

let session = null; // { token, commune, displayName } khi đăng nhập tài khoản xã
let legacyMode = false;

function showSubmitForm() {
  document.getElementById("login-section").style.display = "none";
  document.getElementById("submit-section").style.display = "block";
  const banner = document.getElementById("banner");
  if (session) {
    banner.style.display = "block";
    banner.textContent = "Đã đăng nhập: " + session.displayName + " (" + session.commune + ")";
    document.getElementById("legacy-fields").style.display = "none";
  } else {
    banner.style.display = "none";
    document.getElementById("legacy-fields").style.display = "block";
  }
}

document.getElementById("legacy-toggle").addEventListener("click", () => {
  legacyMode = true; session = null; showSubmitForm();
});

document.getElementById("login-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const msg = document.getElementById("login-msg");
  const username = document.getElementById("login-username").value;
  const password = document.getElementById("login-password").value;
  try {
    const resp = await fetch("/xa/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await resp.json();
    if (!data.ok) { msg.className = "err"; msg.textContent = "Lỗi: " + data.error; return; }
    session = { token: data.result.token, commune: data.result.commune, displayName: data.result.display_name };
    showSubmitForm();
  } catch (e) {
    msg.className = "err"; msg.textContent = "Không kết nối được máy chủ chính. Nếu máy chủ đang offline, hãy dùng đường dẫn dự phòng do CDC cung cấp.";
  }
});

document.getElementById("f").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target;
  const msg = document.getElementById("msg");
  const fileInput = form.file;
  if (!fileInput.files.length) return;
  const file = fileInput.files[0];
  const reader = new FileReader();
  form.querySelector("button").disabled = true;
  reader.onload = async () => {
    try {
      const base64 = reader.result.split(",")[1];
      const payload = {
        week: form.week.value, submitted_by: form.submitted_by.value,
        file_name: file.name, content_base64: base64,
      };
      const headers = { "Content-Type": "application/json" };
      if (session) {
        payload.commune_token = session.token;
      } else {
        payload.commune = form.commune.value;
        headers["X-GSBTN-Password"] = form.password.value;
      }
      const resp = await fetch("/queue/submit", { method: "POST", headers, body: JSON.stringify(payload) });
      const data = await resp.json();
      if (data.ok) {
        msg.className = "ok"; msg.textContent = "Đã nộp vào hàng đợi. Mã hàng đợi #" + data.result.queue_id + ". CDC sẽ nhập vào hệ thống.";
        form.reset(); document.getElementById("week").value = isoWeek(new Date());
      } else {
        msg.className = "err"; msg.textContent = "Lỗi: " + (data.error || "không xác định");
      }
    } catch (e) {
      msg.className = "err"; msg.textContent = "Không kết nối được máy chủ chính. Nếu máy chủ đang offline, hãy dùng đường dẫn dự phòng do CDC cung cấp.";
    } finally {
      form.querySelector("button").disabled = false;
    }
  };
  reader.readAsDataURL(file);
});
</script>
</body>
</html>
"""

CDC_QUEUE_PAGE_HTML = """<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hàng đợi nhập liệu — CDC</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 24px; color: #1f2937; }
  h1 { font-size: 1.25rem; }
  table { border-collapse: collapse; width: 100%; margin-top: 16px; }
  th, td { border: 1px solid #e2e8f0; padding: 6px 10px; text-align: left; font-size: 0.9rem; }
  th { background: #f1f5f9; }
  tr.cho_nhap { background: #fff7d6; }
  tr.dang_nhap { background: #e0f2fe; }
  tr.da_nhap { background: #f0fdf4; }
  tr.loi { background: #fee2e2; }
  button { padding: 6px 10px; cursor: pointer; }
  #toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  input { padding: 6px; }
</style>
</head>
<body>
<h1>Hàng đợi nhập liệu — chia theo xã</h1>
<div id="toolbar">
  <label>Mật khẩu: <input type="password" id="pw"></label>
  <button id="reload">Tải danh sách</button>
  <button id="sync">Đồng bộ máy chủ phụ</button>
</div>
<div id="msg"></div>
<div id="groups"></div>

<h2>Quản lý tài khoản xã</h2>
<form id="account-form" style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
  <input name="commune" placeholder="Xã / phường" required>
  <input name="username" placeholder="Tên đăng nhập" required>
  <input name="password" type="password" placeholder="Mật khẩu (tối thiểu 8 ký tự)" required>
  <input name="display_name" placeholder="Tên hiển thị (không bắt buộc)">
  <button type="submit">Tạo tài khoản</button>
</form>
<div id="account-msg"></div>
<table id="account-table"><tr><th>Xã</th><th>Tên đăng nhập</th><th>Trạng thái</th><th>Đăng nhập gần nhất</th><th></th></tr></table>

<h2>Nhật ký kiểm toán</h2>
<button id="reload-audit">Tải nhật ký gần đây</button>
<table id="audit-table"><tr><th>Thời điểm</th><th>Hành động</th><th>Người thực hiện</th><th>Xã</th><th>Chi tiết</th></tr></table>

<script>
async function rpc(fn, args, kwargs) {
  const resp = await fetch("/rpc", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-GSBTN-Password": document.getElementById("pw").value },
    body: JSON.stringify({ function: fn, args: args || [], kwargs: kwargs || {} }),
  });
  const data = await resp.json();
  if (!data.ok) throw new Error(data.error || "Lỗi không xác định");
  return data.result;
}

async function syncSecondary() {
  const msg = document.getElementById("msg");
  msg.textContent = "Đang đồng bộ máy chủ phụ...";
  try {
    const resp = await fetch("/queue/sync-secondary", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-GSBTN-Password": document.getElementById("pw").value },
      body: "{}",
    });
    const data = await resp.json();
    if (!data.ok) throw new Error(data.error || "Lỗi không xác định");
    msg.textContent = "Đã kéo " + data.result.pulled_count + "/" + data.result.pending_count + " mục từ máy chủ phụ." +
      (data.result.errors.length ? " Lỗi: " + data.result.errors.length + " dòng." : "");
    await load();
  } catch (e) {
    msg.textContent = "Lỗi đồng bộ máy chủ phụ: " + e.message;
  }
}
document.getElementById("sync").addEventListener("click", syncSecondary);

const STATUS_LABEL = { cho_nhap: "Chờ nhập", dang_nhap: "Đang nhập...", da_nhap: "Đã nhập", loi: "Lỗi" };
const SOURCE_LABEL = { server_chinh: "Trực tiếp", server_phu: "Qua máy chủ phụ" };

async function load() {
  const msg = document.getElementById("msg");
  const container = document.getElementById("groups");
  msg.textContent = "Đang tải..."; container.innerHTML = "";
  try {
    const items = await rpc("list_import_queue");
    msg.textContent = items.length + " mục trong hàng đợi.";
    const byCommune = {};
    for (const item of items) { (byCommune[item.commune] = byCommune[item.commune] || []).push(item); }
    for (const commune of Object.keys(byCommune).sort()) {
      const h = document.createElement("h2"); h.textContent = commune; container.appendChild(h);
      const table = document.createElement("table");
      table.innerHTML = "<tr><th>Tuần</th><th>File</th><th>Nguồn</th><th>Trạng thái</th><th>Nhận lúc</th><th>Người nộp</th><th></th></tr>";
      for (const item of byCommune[commune]) {
        const tr = document.createElement("tr"); tr.className = item.status;
        tr.innerHTML = "<td>" + item.week + "</td><td>" + item.file_name + "</td><td>" + (SOURCE_LABEL[item.source] || item.source) +
          "</td><td>" + (STATUS_LABEL[item.status] || item.status) + (item.error_message ? " — " + item.error_message : "") +
          "</td><td>" + item.received_at + "</td><td>" + (item.submitted_by || "") + "</td><td></td>";
        if (item.status === "cho_nhap") {
          const btn = document.createElement("button"); btn.textContent = "Nhập vào CSDL";
          btn.onclick = async () => {
            btn.disabled = true;
            try { await rpc("import_queue_item", [item.id]); await load(); }
            catch (e) { alert("Không thể nhập: " + e.message); btn.disabled = false; }
          };
          tr.lastElementChild.appendChild(btn);
        }
        table.appendChild(tr);
      }
      container.appendChild(table);
    }
  } catch (e) {
    msg.textContent = "Lỗi: " + e.message;
  }
}
document.getElementById("reload").addEventListener("click", load);
load();

async function loadAccounts() {
  const table = document.getElementById("account-table");
  table.querySelectorAll("tr:not(:first-child)").forEach((tr) => tr.remove());
  try {
    const accounts = await rpc("list_commune_accounts");
    for (const acc of accounts) {
      const tr = document.createElement("tr");
      tr.innerHTML = "<td>" + acc.commune + "</td><td>" + acc.username + "</td><td>" +
        (acc.active ? "Đang hoạt động" : "Đã khoá") + "</td><td>" + (acc.last_login_at || "Chưa đăng nhập") + "</td><td></td>";
      const toggleBtn = document.createElement("button");
      toggleBtn.textContent = acc.active ? "Khoá tài khoản" : "Mở khoá";
      toggleBtn.onclick = async () => {
        try { await rpc("set_commune_account_active", [acc.id, !acc.active]); await loadAccounts(); }
        catch (e) { alert("Không thể cập nhật: " + e.message); }
      };
      const resetBtn = document.createElement("button");
      resetBtn.textContent = "Đặt lại mật khẩu";
      resetBtn.onclick = async () => {
        const newPassword = prompt("Mật khẩu mới cho " + acc.username + " (tối thiểu 8 ký tự):");
        if (!newPassword) return;
        try { await rpc("reset_commune_account_password", [acc.id, newPassword]); alert("Đã đặt lại mật khẩu."); }
        catch (e) { alert("Không thể đặt lại: " + e.message); }
      };
      tr.lastElementChild.appendChild(toggleBtn); tr.lastElementChild.appendChild(resetBtn);
      table.appendChild(tr);
    }
  } catch (e) {
    document.getElementById("account-msg").textContent = "Lỗi: " + e.message;
  }
}

document.getElementById("account-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target;
  const msg = document.getElementById("account-msg");
  try {
    await rpc("create_commune_account", [form.commune.value, form.username.value, form.password.value, form.display_name.value]);
    msg.textContent = "Đã tạo tài khoản."; form.reset(); await loadAccounts();
  } catch (e) {
    msg.textContent = "Lỗi: " + e.message;
  }
});

const AUDIT_ACTION_LABEL = {
  login: "Đăng nhập", login_failed: "Đăng nhập thất bại", queue_submit: "Nộp vào hàng đợi",
  import_queue_item: "Nhập vào CSDL", merge_duplicate_records: "Hợp nhất trùng", remove_duplicate_records: "Loại trùng",
  restore_duplicate_action: "Khôi phục", export_cases_by_commune: "Xuất theo xã", archive_old_queue_files: "Dọn dẹp hàng đợi",
  create_commune_account: "Tạo tài khoản xã", enable_commune_account: "Mở khoá tài khoản xã",
  disable_commune_account: "Khoá tài khoản xã", reset_commune_account_password: "Đặt lại mật khẩu xã",
};

async function loadAudit() {
  const table = document.getElementById("audit-table");
  table.querySelectorAll("tr:not(:first-child)").forEach((tr) => tr.remove());
  try {
    const logs = await rpc("list_audit_log", [], { limit: 200 });
    for (const item of logs) {
      const tr = document.createElement("tr");
      tr.innerHTML = "<td>" + item.created_at + "</td><td>" + (AUDIT_ACTION_LABEL[item.action] || item.action) +
        "</td><td>" + item.actor + "</td><td>" + (item.commune || "") + "</td><td>" + (item.detail || "") + "</td>";
      table.appendChild(tr);
    }
  } catch (e) {
    alert("Không thể tải nhật ký: " + e.message);
  }
}
document.getElementById("reload-audit").addEventListener("click", loadAudit);
</script>
</body>
</html>
"""


def configure_windows_firewall(port: int) -> dict[str, Any]:
    if os.name != "nt":
        return {"ok": False, "message": "Chỉ cấu hình Windows Firewall trên Windows."}
    rule_tcp = f"GSBTN Server TCP {int(port)}"
    rule_udp = "GSBTN Discovery UDP 8766"
    commands = [
        f'netsh advfirewall firewall delete rule name="{rule_tcp}"',
        f'netsh advfirewall firewall add rule name="{rule_tcp}" dir=in action=allow protocol=TCP localport={int(port)} profile=private',
        f'netsh advfirewall firewall delete rule name="{rule_udp}"',
        f'netsh advfirewall firewall add rule name="{rule_udp}" dir=in action=allow protocol=UDP localport=8766 profile=private',
    ]
    script = "; ".join(f"& {command}" for command in commands)
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=60,
        )
        if completed.returncode == 0:
            return {"ok": True, "message": "Đã tạo quy tắc tường lửa cho mạng Riêng tư."}
        return {"ok": False, "message": (completed.stderr or completed.stdout or "Cần chạy ứng dụng bằng quyền quản trị.").strip()}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


class ApiServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], config: DeploymentConfig):
        super().__init__(address, ApiHandler)
        self.config = config
        self.clients: dict[str, dict[str, Any]] = {}
        self.request_log: deque[dict[str, Any]] = deque(maxlen=500)
        self.backup_in_progress = False
        self.state_lock = threading.RLock()
        self._queue_submit_times: dict[str, deque[float]] = {}

    def check_queue_submit_rate(self, rate_key: str) -> bool:
        """Giới hạn số lần nộp hàng đợi mỗi (IP, xã) trong một cửa sổ thời gian trượt.

        Khoá theo cặp (IP, xã) chứ không chỉ IP: khi Google Apps Script chuyển tiếp trực tiếp
        cho nhiều xã, mọi request đều mang IP đi ra của Google — nếu khoá theo IP đơn thuần,
        một xã gửi dồn dập có thể khiến các xã khác dùng chung đường chuyển tiếp bị chặn oan.
        Tránh một máy (vô tình lỗi hoặc cố ý) gửi liên tục nhiều file lớn làm đầy RAM khi đọc
        request hoặc đầy ổ đĩa QUEUE_DIR. Trả False nếu đã vượt ngưỡng.
        """
        now = time.monotonic()
        with self.state_lock:
            times = self._queue_submit_times.setdefault(rate_key, deque())
            while times and now - times[0] > QUEUE_SUBMIT_RATE_WINDOW_SECONDS:
                times.popleft()
            if len(times) >= QUEUE_SUBMIT_RATE_LIMIT:
                return False
            times.append(now)
            return True

    def register_request(self, client_ip: str, path: str, method: str, ok: bool = True) -> None:
        now = datetime.now().isoformat(sep=" ", timespec="seconds")
        with self.state_lock:
            client = self.clients.setdefault(client_ip, {"ip": client_ip, "first_seen": now, "requests": 0})
            client["last_seen"] = now
            client["requests"] = int(client.get("requests", 0)) + 1
            client["last_path"] = path
            self.request_log.appendleft({"time": now, "ip": client_ip, "method": method, "path": path, "ok": ok})

    def status_payload(self) -> dict[str, Any]:
        with self.state_lock:
            clients = sorted(self.clients.values(), key=lambda item: str(item.get("last_seen", "")), reverse=True)
            logs = list(self.request_log)[:100]
        return {
            "running": True,
            "address": f"http://{get_lan_ip()}:{self.server_port}",
            "port": self.server_port,
            "server_name": self.config.server_name or socket.gethostname(),
            "password_required": bool(self.config.password),
            "backup_in_progress": self.backup_in_progress,
            "client_count": len(clients),
            "clients": clients,
            "logs": logs,
        }


class ApiHandler(BaseHTTPRequestHandler):
    server: ApiServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    @property
    def client_ip(self) -> str:
        return str(self.client_address[0])

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(_jsonable(payload), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _write_html(self, status: int, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        expected = self.server.config.password
        return not expected or self.headers.get("X-GSBTN-Password", "") == expected

    def _reject_auth(self) -> None:
        self.server.register_request(self.client_ip, self.path, self.command, False)
        self._write_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "Sai mật khẩu máy chủ."})

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path in PUBLIC_HTML_PAGES:
            self.server.register_request(self.client_ip, path, "GET", True)
            html = XA_UPLOAD_PAGE_HTML if path == "/xa" else CDC_QUEUE_PAGE_HTML
            self._write_html(HTTPStatus.OK, html); return
        if not self._authorized():
            self._reject_auth(); return
        if path == "/health":
            payload = {
                "ok": True, "app": core.APP_NAME, "version": core.VERSION, "mode": "server",
                "server_name": self.server.config.server_name or socket.gethostname(),
                "lan_ip": get_lan_ip(), "port": self.server.server_port,
                "password_required": bool(self.server.config.password),
                "read_only": self.server.backup_in_progress,
            }
        elif path == "/status":
            payload = {"ok": True, "result": self.server.status_payload()}
        else:
            self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Không tìm thấy endpoint."}); return
        self.server.register_request(self.client_ip, path, "GET", True)
        self._write_json(HTTPStatus.OK, payload)

    def _drain_body(self, length: int) -> None:
        """Đọc bỏ phần thân request chưa xử lý trước khi trả lỗi sớm.

        Nếu không đọc hết, phần thân còn lại trong socket sẽ bị hiểu nhầm là đầu request kế
        tiếp trên cùng kết nối keep-alive (HTTP/1.1), làm lệch toàn bộ các request sau đó.
        """
        if length > 0:
            try:
                self.rfile.read(length)
            except Exception:
                pass

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        path = self.path.rstrip("/")
        # "/xa/login" luôn công khai (đăng nhập không thể đòi hỏi đã đăng nhập). "/queue/submit"
        # tự xử lý xác thực bên trong _handle_queue_submit — chấp nhận CẢ token đăng nhập xã LẪN
        # mật khẩu máy chủ dùng chung (không "chỉ dùng token khi đã có tài khoản" như trước),
        # vì Google Apps Script khi chuyển tiếp trực tiếp chỉ biết mật khẩu dùng chung, không có
        # token của từng xã — hai đường xác thực cần cùng tồn tại song song thay vì loại trừ nhau.
        exempt_from_shared_password = path in ("/xa/login", "/queue/submit")
        if not exempt_from_shared_password and not self._authorized():
            self._drain_body(max(length, 0))
            self._reject_auth(); return
        if length < 0 or length > MAX_REQUEST_BYTES:
            self._write_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"ok": False, "error": "Yêu cầu vượt giới hạn 110 MB."})
            return
        try:
            payload = json.loads((self.rfile.read(length) if length else b"{}").decode("utf-8"))
            log_path = path
            if path == "/queue/submit":
                rate_key = f"{self.client_ip}:{str(payload.get('commune', ''))[:80]}"
                if not self.server.check_queue_submit_rate(rate_key):
                    self.server.register_request(self.client_ip, path, "POST", False)
                    self._write_json(
                        HTTPStatus.TOO_MANY_REQUESTS,
                        {"ok": False, "error": "Vượt giới hạn số lần nộp trong 5 phút. Hãy thử lại sau."},
                    )
                    return
            if path == "/rpc":
                log_path = f"/rpc:{str(payload.get('function', 'unknown'))}"
                result = self._handle_rpc(payload)
            elif path == "/import":
                if self.server.backup_in_progress:
                    raise RuntimeError("Máy chủ đang sao lưu; tạm thời chỉ cho phép đọc dữ liệu.")
                result = self._handle_import(payload)
            elif path == "/xa/login":
                result = self._handle_commune_login(payload)
            elif path == "/queue/submit":
                if self.server.backup_in_progress:
                    raise RuntimeError("Máy chủ đang sao lưu; tạm thời chỉ cho phép đọc dữ liệu.")
                result = self._handle_queue_submit(payload)
            elif path == "/queue/sync-secondary":
                if self.server.backup_in_progress:
                    raise RuntimeError("Máy chủ đang sao lưu; tạm thời chỉ cho phép đọc dữ liệu.")
                result = secondary_sync.pull_secondary_queue(
                    self.server.config.secondary_webapp_url, self.server.config.secondary_shared_key, db_path=core.DB_PATH,
                )
            else:
                self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Không tìm thấy endpoint."}); return
            self.server.register_request(self.client_ip, log_path, "POST", True)
            self._write_json(HTTPStatus.OK, {"ok": True, "result": result})
        except Exception as exc:
            self.server.register_request(self.client_ip, locals().get("log_path", path), "POST", False)
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

    def _handle_rpc(self, payload: dict[str, Any]) -> Any:
        function_name = str(payload.get("function", ""))
        if function_name not in READ_FUNCTIONS | WRITE_FUNCTIONS:
            raise ValueError("Hàm RPC không được phép.")
        args, kwargs = payload.get("args") or [], payload.get("kwargs") or {}
        if not isinstance(args, list) or not isinstance(kwargs, dict):
            raise ValueError("args/kwargs không hợp lệ.")
        kwargs.pop("db_path", None)
        if function_name in DB_FUNCTIONS:
            kwargs["db_path"] = core.DB_PATH
        if function_name in WRITE_FUNCTIONS and function_name != "create_backup" and self.server.backup_in_progress:
            raise RuntimeError("Máy chủ đang sao lưu; tạm thời chỉ cho phép đọc dữ liệu.")
        if function_name in AUDITED_FUNCTIONS and not kwargs.get("actor"):
            kwargs["actor"] = f"LAN:{self.client_ip}"
        function = getattr(core, function_name, None)
        if not callable(function):
            raise ValueError(f"Máy chủ chưa hỗ trợ hàm {function_name}.")
        if function_name == "create_backup":
            with self.server.state_lock:
                if self.server.backup_in_progress:
                    raise RuntimeError("Máy chủ đang thực hiện một bản sao lưu khác.")
                self.server.backup_in_progress = True
            try:
                return function(*args, **kwargs)
            finally:
                with self.server.state_lock:
                    self.server.backup_in_progress = False
        return function(*args, **kwargs)

    def _handle_import(self, payload: dict[str, Any]) -> Any:
        name = Path(str(payload.get("file_name", "du_lieu.xlsx"))).name
        content = payload.get("content_base64")
        if not isinstance(content, str) or not content:
            raise ValueError("Thiếu nội dung file Excel.")
        if Path(name).suffix.lower() not in {".xlsx", ".xlsm"}:
            raise ValueError("Chỉ chấp nhận file XLSX hoặc XLSM.")
        data = base64.b64decode(content.encode("ascii"), validate=True)
        if len(data) > 100 * 1024 * 1024:
            raise ValueError("File vượt quá giới hạn 100 MB.")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / name
            path.write_bytes(data)
            return core.import_excel(path, core.DB_PATH)

    def _handle_commune_login(self, payload: dict[str, Any]) -> Any:
        username = str(payload.get("username", ""))
        password = str(payload.get("password", ""))
        account = core.verify_commune_account(username, password, db_path=core.DB_PATH)
        if not account:
            raise ValueError("Sai tên đăng nhập hoặc mật khẩu.")
        config = ensure_web_token_secret(self.server.config)
        token = core.issue_commune_token(
            account["id"], account["commune"], account["username"], config.web_token_secret
        )
        return {
            "token": token, "commune": account["commune"], "username": account["username"],
            "display_name": account["display_name"],
        }

    def _handle_queue_submit(self, payload: dict[str, Any]) -> Any:
        """Xác thực nộp hàng đợi — chấp nhận HAI đường song song, không loại trừ nhau:

        1. Token đăng nhập tài khoản xã (``commune_token``) — dùng bởi trang ``/xa`` sau khi xã
           đăng nhập. ``commune`` khi đó lấy từ token, không tin trường tự khai trên form.
        2. Mật khẩu máy chủ dùng chung (``X-GSBTN-Password``) — dùng bởi máy trạm nội bộ và bởi
           Google Apps Script khi chuyển tiếp trực tiếp (GAS chỉ biết một mật khẩu dùng chung
           cho mọi xã, không có token riêng từng xã). ``commune`` khi đó lấy từ trường tự khai.

        Không còn bắt buộc token chỉ vì hệ thống đã có tài khoản xã — nếu không thì đường
        chuyển tiếp từ Google Apps Script (không có token) sẽ luôn bị chặn.
        """
        content = payload.get("content_base64")
        if not isinstance(content, str) or not content:
            raise ValueError("Thiếu nội dung file Excel.")
        data = base64.b64decode(content.encode("ascii"), validate=True)
        commune = str(payload.get("commune", ""))
        submitted_by = str(payload.get("submitted_by", ""))
        token = str(payload.get("commune_token") or "")
        claims = core.verify_commune_token(token, self.server.config.web_token_secret) if token else None
        if claims:
            commune = claims["commune"]
            submitted_by = submitted_by or claims.get("username", "")
        elif not self._authorized():
            raise ValueError("Cần đăng nhập tài khoản xã hoặc mật khẩu máy chủ hợp lệ để nộp dữ liệu.")
        return core.queue_submit(
            commune,
            str(payload.get("week", "")),
            str(payload.get("file_name", "du_lieu.xlsx")),
            data,
            source="server_chinh",
            submitted_by=submitted_by,
            db_path=core.DB_PATH,
        )


class LanServerController:
    def __init__(self, config: DeploymentConfig | None = None):
        self.config = config or load_config()
        self.httpd: ApiServer | None = None
        self.thread: threading.Thread | None = None
        self.discovery: DiscoveryResponder | None = None
        self.last_error = ""

    @property
    def running(self) -> bool:
        return bool(self.httpd and self.thread and self.thread.is_alive())

    @property
    def port(self) -> int:
        return int(self.httpd.server_port if self.httpd else self.config.server_port)

    @property
    def address(self) -> str:
        return f"http://{get_lan_ip()}:{self.port}"

    def start(self) -> str:
        if self.running:
            return self.address
        core.init_db()
        if not port_available(self.config.server_host, self.config.server_port):
            raise OSError(f"Cổng {self.config.server_port} đang được chương trình khác sử dụng.")
        try:
            self.config = ensure_web_token_secret(self.config)
            self.httpd = ApiServer((self.config.server_host, self.config.server_port), self.config)
            self.thread = threading.Thread(target=self.httpd.serve_forever, name="GSBTN-LAN-Server", daemon=True)
            self.thread.start()
            self.last_error = ""
            if self.config.discovery_enabled:
                self.discovery = DiscoveryResponder(
                    self.port, core.APP_NAME, core.VERSION, bool(self.config.password), self.config.server_name
                )
                try:
                    self.discovery.start()
                except OSError as exc:
                    self.last_error = f"Server chạy nhưng không mở được tự dò LAN: {exc}"
            return self.address
        except Exception as exc:
            self.httpd = None; self.thread = None; self.last_error = str(exc)
            raise

    def stop(self) -> None:
        if self.discovery:
            self.discovery.stop()
        self.discovery = None
        if self.httpd:
            self.httpd.shutdown(); self.httpd.server_close()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3)
        self.httpd = None; self.thread = None

    def status(self) -> dict[str, Any]:
        if self.httpd:
            payload = self.httpd.status_payload()
            payload["discovery_running"] = bool(self.discovery and self.discovery.running)
            payload["last_error"] = self.last_error
            return payload
        return {
            "running": False, "address": self.address, "port": self.config.server_port,
            "server_name": self.config.server_name or socket.gethostname(),
            "password_required": bool(self.config.password), "backup_in_progress": False,
            "client_count": 0, "clients": [], "logs": [], "discovery_running": False,
            "last_error": self.last_error,
        }
