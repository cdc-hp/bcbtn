"""`/cdc/nhat-ky` — Giai đoạn 6 (xem TASKS.md): xem/lọc nhật ký thao tác qua Web, tái dùng nguyên
`core.list_audit_log` (đã có sẵn tham số action/commune/actor/ip/since/until từ Giai đoạn 2).
Chỉ super_admin/admin xem được — nhật ký lộ IP + toàn bộ hoạt động hệ thống, nhạy cảm hơn mức
"chỉ xem" thông thường."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import core
from webapp import TEMPLATES_DIR, auth
from webapp.config import WebAppSettings
from webapp.dependencies import get_settings_dep, require_role
from webapp.services.pagination import paginate

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)

CAN_VIEW_ROLES = (core.CDC_ROLE_SUPER_ADMIN, core.CDC_ROLE_ADMIN)


@router.get("/cdc/nhat-ky", response_class=HTMLResponse)
def view_log(
    request: Request, action: str = "", commune: str = "", actor: str = "", ip: str = "",
    since: str = "", until: str = "", page: int = 1,
    user: auth.CurrentUser = Depends(require_role(*CAN_VIEW_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    rows = core.list_audit_log(
        action=action, commune=commune, actor=actor, ip=ip, since=since, until=until,
        limit=2000, db_path=settings.db_path,
    )
    page_rows, page_info = paginate(rows, page)
    filters = {"action": action, "commune": commune, "actor": actor, "ip": ip, "since": since, "until": until}
    active_filters = {k: v for k, v in filters.items() if v}
    pagination_base = "/cdc/nhat-ky?" + (urlencode(active_filters) + "&" if active_filters else "") + "page="
    token = auth.get_csrf_token(request)
    response = templates.TemplateResponse(request, "audit_log.html", {
        "user": user, "csrf_token": token, "active": "nhat-ky", "rows": page_rows,
        "filters": filters, "total": page_info["total"],
        "page": page_info["page"], "total_pages": page_info["total_pages"], "pagination_base": pagination_base,
    })
    auth.set_csrf_cookie(response, request, token)
    return response
