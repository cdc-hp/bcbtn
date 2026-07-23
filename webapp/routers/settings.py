"""`/cdc/cau-hinh` — Giai đoạn 8 (xem TASKS.md): cấu hình triển khai qua Web (cổng/địa chỉ, tên
miền công khai, GAS URL/API key, chu kỳ đồng bộ máy chủ phụ, thư mục sao lưu) — chỉ
`super_admin`. Tài khoản super_admin đầu tiên đã tạo qua `/cdc/setup` (Giai đoạn 2); trang này
KHÔNG lặp lại bước bootstrap đó, chỉ chỉnh cấu hình triển khai sau khi đã đăng nhập.

Đổi `server_host`/`server_port` cần khởi động lại tiến trình Uvicorn mới có hiệu lực (không thể
tự đổi cổng đang lắng nghe khi đang chạy) — trang cung cấp nút "Khởi động lại dịch vụ" gọi
`service_windows.restart_service()`, chỉ thật sự hoạt động khi Web App đã được cài làm dịch vụ
Windows (xem `service_windows.py`); nếu không, trả thông báo lỗi rõ ràng thay vì giả vờ thành
công."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import backup_manager
import core
import deployment_config
import service_windows
from webapp import auth
from webapp.config import WebAppSettings
from webapp.dependencies import ForbiddenError, get_settings_dep, require_role

router = APIRouter()
templates = Jinja2Templates(directory="webapp/templates")

CAN_CONFIGURE_ROLES = (core.CDC_ROLE_SUPER_ADMIN,)


def _redirect(msg: str = "", err: str = "") -> RedirectResponse:
    url = "/cdc/cau-hinh"
    if msg:
        url += f"?msg={quote(msg)}"
    elif err:
        url += f"?err={quote(err)}"
    return RedirectResponse(url, status_code=303)


@router.get("/cdc/cau-hinh", response_class=HTMLResponse)
def view(
    request: Request, msg: str = "", err: str = "",
    user: auth.CurrentUser = Depends(require_role(*CAN_CONFIGURE_ROLES)),
):
    config = deployment_config.load_config()
    policy = backup_manager.load_policy()
    backup_destination = policy.destination or str(backup_manager.backup_directory(policy))

    token = auth.get_csrf_token(request)
    response = templates.TemplateResponse(request, "settings.html", {
        "user": user, "csrf_token": token, "active": "cau-hinh",
        "config": config, "backup_destination": backup_destination,
        "service_status": service_windows.query_status(), "msg": msg, "err": err,
    })
    auth.set_csrf_cookie(response, request, token)
    return response


@router.post("/cdc/cau-hinh", response_class=HTMLResponse)
async def save(
    request: Request, csrf_token: str = Form(""),
    server_host: str = Form("0.0.0.0"), server_port: int = Form(8765), public_url: str = Form(""),
    gas_api_key: str = Form(""), secondary_webapp_url: str = Form(""), secondary_shared_key: str = Form(""),
    secondary_sync_interval_minutes: int = Form(20), backup_destination: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_CONFIGURE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")

    config = deployment_config.load_config()
    port_before, host_before = config.server_port, config.server_host
    config.server_host = server_host.strip() or "0.0.0.0"
    config.server_port = server_port
    config.public_url = public_url.strip()
    config.gas_api_key = gas_api_key.strip() or config.gas_api_key
    config.secondary_webapp_url = secondary_webapp_url.strip()
    config.secondary_shared_key = secondary_shared_key or config.secondary_shared_key
    config.secondary_sync_interval_minutes = secondary_sync_interval_minutes
    deployment_config.save_config(config)

    policy = backup_manager.load_policy()
    policy.destination = backup_destination.strip()
    backup_manager.save_policy(policy)

    core.log_audit("save_deployment_settings_web", actor=user.username, db_path=settings.db_path)

    needs_restart = config.server_host != host_before or config.server_port != port_before
    msg = "Đã lưu cấu hình."
    if needs_restart:
        msg += " Đổi cổng/địa chỉ cần khởi động lại dịch vụ để có hiệu lực."
    return _redirect(msg=msg)


@router.post("/cdc/cau-hinh/khoi-dong-lai", response_class=HTMLResponse)
def restart(
    request: Request, csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_CONFIGURE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    result = service_windows.restart_service()
    core.log_audit(
        "restart_service_web" if result["ok"] else "restart_service_web_failed",
        actor=user.username, detail=result["message"], db_path=settings.db_path,
    )
    if result["ok"]:
        return _redirect(msg=result["message"])
    return _redirect(err=result["message"])
