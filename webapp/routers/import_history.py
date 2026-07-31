"""`/cdc/lich-su-nhap` — lịch sử các lần nhập Excel (bảng `import_batches`), cho phép xóa nguyên
một lần nhập (mọi ca bệnh/ổ dịch sinh ra từ đúng file + thời điểm nhập đó) khi CDC phát hiện nhập
nhầm file — xem `core.delete_import_batch`."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import core
from webapp import TEMPLATES_DIR, auth
from webapp.config import WebAppSettings
from webapp.dependencies import ForbiddenError, get_settings_dep, require_role
from webapp.services.pagination import paginate

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)

CAN_VIEW_ROLES = (core.CDC_ROLE_SUPER_ADMIN, core.CDC_ROLE_ADMIN, core.CDC_ROLE_DATA_OPERATOR)
CAN_DELETE_ROLES = (core.CDC_ROLE_SUPER_ADMIN, core.CDC_ROLE_ADMIN)
ENTITY_LABELS = {"case": "Ca bệnh", "outbreak": "Ổ dịch"}


@router.get("/cdc/lich-su-nhap", response_class=HTMLResponse)
def list_batches(
    request: Request, msg: str = "", err: str = "", page: int = 1,
    user: auth.CurrentUser = Depends(require_role(*CAN_VIEW_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    rows = core.list_import_batches(db_path=settings.db_path, limit=2000)
    for row in rows:
        row["entity_label"] = ENTITY_LABELS.get(row["entity_type"], row["entity_type"])
    page_rows, page_info = paginate(rows, page)
    token = auth.get_csrf_token(request)
    response = templates.TemplateResponse(request, "import_history.html", {
        "user": user, "csrf_token": token, "active": "lich-su-nhap",
        "rows": page_rows, "total": page_info["total"],
        "page": page_info["page"], "total_pages": page_info["total_pages"],
        "pagination_base": "/cdc/lich-su-nhap?page=",
        "can_delete": user.has_role(*CAN_DELETE_ROLES), "msg": msg, "err": err,
    })
    auth.set_csrf_cookie(response, request, token)
    return response


@router.post("/cdc/lich-su-nhap/{batch_id}/xoa", response_class=HTMLResponse)
async def delete_batch(
    batch_id: int, request: Request, csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_DELETE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    try:
        result = core.delete_import_batch(batch_id, db_path=settings.db_path, actor=user.username)
    except ValueError as exc:
        return RedirectResponse(f"/cdc/lich-su-nhap?err={quote(str(exc))}", status_code=303)
    label = ENTITY_LABELS.get(result["entity_type"], result["entity_type"])
    msg = f"Đã xóa {result['deleted_count']} {label.lower()} từ file {result['file_name']}."
    return RedirectResponse(f"/cdc/lich-su-nhap?msg={quote(msg)}", status_code=303)
