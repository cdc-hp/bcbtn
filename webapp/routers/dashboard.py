"""`/cdc/dashboard` — Section 6 của nhiệm vụ Web App (xem TASKS.md Giai đoạn 4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import backup_manager
import core
from webapp import TEMPLATES_DIR, auth, scheduler
from webapp.config import WebAppSettings
from webapp.dependencies import ForbiddenError, get_settings_dep, require_password_current, require_role
from webapp.services import dashboard_query

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)

CAN_SYNC_ROLES = (core.CDC_ROLE_SUPER_ADMIN, core.CDC_ROLE_ADMIN, core.CDC_ROLE_DATA_OPERATOR)


@router.get("/cdc/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    disease: str = "", report_week: str = "",
    user: auth.CurrentUser = Depends(require_password_current),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    stats = dashboard_query.dashboard_metrics(disease=disease, db_path=settings.db_path)
    current_week = core.current_iso_week()
    # Tuần xem "xã nào chưa nộp" — MẶC ĐỊNH tuần TRƯỚC (vd hôm nay tuần 31 thì mặc định tuần 30),
    # không phải tuần hiện tại: tuần hiện tại chưa kết thúc nên chưa thể coi xã nào đó là "thiếu"
    # báo cáo. CDC vẫn chọn lại được tuần khác qua ô chọn tuần trên dashboard.
    if not core.is_valid_iso_week(report_week):
        report_week = core.shift_iso_week(current_week, -1)

    queue_pending = len(core.list_import_queue(status="cho_nhap", limit=2000, db_path=settings.db_path))
    queue_error = len(core.list_import_queue(status="loi", limit=2000, db_path=settings.db_path))
    report_week_items = core.list_import_queue(week=report_week, limit=2000, db_path=settings.db_path)
    communes_submitted = sorted({item["commune"] for item in report_week_items})
    # Danh sách "xã/phường/đặc khu" đầy đủ (114 đơn vị, xem core.OFFICIAL_COMMUNES) dùng làm mẫu số
    # để LUÔN tính ra được danh sách CHƯA nộp — không còn phụ thuộc CDC đã tạo tài khoản xã
    # (/cdc/tai-khoan-xa) cho từng đơn vị hay chưa (trước đây nếu chưa có tài khoản nào thì không
    # biết "tổng số" là bao nhiêu, phải hiện tạm danh sách ĐÃ nộp thay vì CHƯA nộp).
    expected_communes = sorted(core.OFFICIAL_COMMUNES)
    communes_missing = [commune for commune in expected_communes if commune not in communes_submitted]
    commune_total = len(expected_communes)
    submit_percent = round(len(set(communes_submitted) & set(expected_communes)) * 100 / commune_total) if commune_total else 0

    if disease:
        case_groups = core.find_duplicate_groups(
            "case", criteria=core.load_case_criteria(), max_records=3000, db_path=settings.db_path,
        )
        outbreak_groups = core.find_duplicate_groups("outbreak", max_records=3000, db_path=settings.db_path)
        duplicate_case_groups = sum(
            1 for group in case_groups
            if any(record.get("main_diagnosis") == disease for record in group.get("records", []))
        )
        duplicate_outbreak_groups = sum(
            1 for group in outbreak_groups
            if any(record.get("disease") == disease for record in group.get("records", []))
        )
    else:
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
        "stats": stats, "current_week": current_week, "report_week": report_week,
        "queue_pending": queue_pending, "queue_error": queue_error,
        "communes_missing": communes_missing,
        "commune_total": commune_total, "submit_percent": submit_percent, "latest_backup": latest_backup,
        "duplicate_groups": duplicate_case_groups + duplicate_outbreak_groups,
        "version": core.VERSION, "sync_status": scheduler.get_status(),
        "disease": disease, "disease_options": dashboard_query.disease_options(settings.db_path),
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
