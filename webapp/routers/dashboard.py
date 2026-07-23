"""`/cdc/dashboard` — Section 6 của nhiệm vụ Web App (xem TASKS.md Giai đoạn 4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import backup_manager
import core
from webapp import auth, scheduler
from webapp.config import WebAppSettings
from webapp.dependencies import ForbiddenError, get_settings_dep, require_password_current, require_role

router = APIRouter()
templates = Jinja2Templates(directory="webapp/templates")

CAN_SYNC_ROLES = (core.CDC_ROLE_SUPER_ADMIN, core.CDC_ROLE_ADMIN, core.CDC_ROLE_DATA_OPERATOR)


@router.get("/cdc/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    user: auth.CurrentUser = Depends(require_password_current),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    stats = core.dashboard_stats(db_path=settings.db_path)
    current_week = core.current_iso_week()

    queue_pending = len(core.list_import_queue(status="cho_nhap", limit=2000, db_path=settings.db_path))
    queue_error = len(core.list_import_queue(status="loi", limit=2000, db_path=settings.db_path))
    this_week_items = core.list_import_queue(week=current_week, limit=2000, db_path=settings.db_path)
    communes_submitted = sorted({item["commune"] for item in this_week_items})
    duplicate_case_groups = core.count_duplicate_groups("case", db_path=settings.db_path)
    duplicate_outbreak_groups = core.count_duplicate_groups("outbreak", db_path=settings.db_path)

    try:
        backups = backup_manager.list_backups()
        latest_backup = backups[0] if backups else None
    except Exception:
        latest_backup = None

    token = auth.get_csrf_token(request)
    response = templates.TemplateResponse(request, "dashboard.html", {
        "user": user, "csrf_token": token, "active": "dashboard",
        "stats": stats, "current_week": current_week,
        "queue_pending": queue_pending, "queue_error": queue_error,
        "communes_submitted": communes_submitted, "latest_backup": latest_backup,
        "duplicate_groups": duplicate_case_groups + duplicate_outbreak_groups,
        "version": core.VERSION, "sync_status": scheduler.get_status(),
        "can_sync": user.has_role(*CAN_SYNC_ROLES),
    })
    auth.set_csrf_cookie(response, request, token)
    return response


@router.post("/cdc/dashboard/dong-bo-may-chu-phu")
def sync_now(
    request: Request, csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_SYNC_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    """`def` thường (không `async`) để FastAPI tự chạy trong luồng riêng (threadpool) — hàm này
    gọi `secondary_sync.pull_secondary_queue` (mạng, có thể tới ``DEFAULT_TIMEOUT`` giây mỗi
    dòng đang chờ), nếu khai `async def` mà gọi thẳng sẽ chặn toàn bộ vòng lặp sự kiện, treo cả
    Web App cho mọi người dùng khác trong lúc chờ."""
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    scheduler.run_sync_once(db_path=settings.db_path)
    return RedirectResponse("/cdc/dashboard", status_code=303)
