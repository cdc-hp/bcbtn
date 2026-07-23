"""`/cdc/dashboard` — Section 6 của nhiệm vụ Web App (xem TASKS.md Giai đoạn 4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import backup_manager
import core
from webapp import auth
from webapp.config import WebAppSettings
from webapp.dependencies import get_settings_dep, require_password_current

router = APIRouter()
templates = Jinja2Templates(directory="webapp/templates")


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
        "version": core.VERSION,
    })
    auth.set_csrf_cookie(response, request, token)
    return response
