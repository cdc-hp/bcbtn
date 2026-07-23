"""`/cdc/hang-doi` — Section 6 của nhiệm vụ Web App: lọc theo xã/tuần/trạng thái/nguồn, xem,
tải file gốc, nhập (một/nhiều), xem lỗi, nhập lại, xoá theo quyền. Chống 2 người cùng nhập 1
file đã có sẵn ở `core.import_queue_item` (UPDATE nguyên tử) — router chỉ cần bắt ValueError."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import core
from webapp import auth
from webapp.config import WebAppSettings
from webapp.dependencies import ForbiddenError, get_settings_dep, require_password_current, require_role
from webapp.services.http import client_ip

router = APIRouter()
templates = Jinja2Templates(directory="webapp/templates")

STATUS_LABELS = {"cho_nhap": "Chờ nhập", "dang_nhap": "Đang nhập...", "da_nhap": "Đã nhập", "loi": "Lỗi"}
SOURCE_LABELS = {"server_chinh": "Trực tiếp", "server_phu": "Qua máy chủ phụ"}

CAN_IMPORT_ROLES = (core.CDC_ROLE_SUPER_ADMIN, core.CDC_ROLE_ADMIN, core.CDC_ROLE_DATA_OPERATOR)
CAN_DELETE_ROLES = (core.CDC_ROLE_SUPER_ADMIN, core.CDC_ROLE_ADMIN)


def _redirect_to_list(request: Request, msg: str = "", err: str = "") -> RedirectResponse:
    qs = request.url.query
    base = "/cdc/hang-doi" + (f"?{qs}" if qs else "")
    sep = "&" if "?" in base else "?"
    if msg:
        base += f"{sep}msg={quote(msg)}"
    elif err:
        base += f"{sep}err={quote(err)}"
    return RedirectResponse(base, status_code=303)


@router.get("/cdc/hang-doi", response_class=HTMLResponse)
def queue_list(
    request: Request,
    commune: str = "", week: str = "", status: str = "", source: str = "",
    msg: str = "", err: str = "",
    user: auth.CurrentUser = Depends(require_password_current),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    items = core.list_import_queue(status=status, commune=commune, week=week, source=source, db_path=settings.db_path)
    rows = []
    for item in items:
        row = dict(item)
        row["status_label"] = STATUS_LABELS.get(item["status"], item["status"])
        row["source_label"] = SOURCE_LABELS.get(item["source"], item["source"])
        rows.append(row)
    token = auth.get_csrf_token(request)
    response = templates.TemplateResponse(request, "queue.html", {
        "user": user, "csrf_token": token, "rows": rows, "active": "hang-doi",
        "filters": {"commune": commune, "week": week, "status": status, "source": source},
        "status_options": STATUS_LABELS, "source_options": SOURCE_LABELS,
        "can_import": user.has_role(*CAN_IMPORT_ROLES), "can_delete": user.has_role(*CAN_DELETE_ROLES),
        "msg": msg, "err": err,
    })
    auth.set_csrf_cookie(response, request, token)
    return response


@router.get("/cdc/hang-doi/{queue_id}/download")
def download_file(
    queue_id: int,
    user: auth.CurrentUser = Depends(require_password_current),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    items = core.list_import_queue(limit=2000, db_path=settings.db_path)
    item = next((i for i in items if i["id"] == queue_id), None)
    if not item:
        raise ForbiddenError("Không tìm thấy mục trong hàng đợi.")
    from pathlib import Path
    file_path = Path(item["file_path"])
    if not file_path.exists():
        raise ForbiddenError("File không còn tồn tại trên máy chủ.")
    return FileResponse(file_path, filename=item["file_name"])


@router.post("/cdc/hang-doi/{queue_id}/import", response_class=HTMLResponse)
async def import_one(
    queue_id: int, request: Request, csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_IMPORT_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    try:
        result = core.import_queue_item(queue_id, db_path=settings.db_path, actor=user.username)
    except ValueError as exc:
        return _redirect_to_list(request, err=str(exc))
    return _redirect_to_list(
        request, msg=f"Đã nhập {result['file_name']}: thêm {result['inserted']}, trùng {result['duplicates']}, bỏ qua {result['skipped']}."
    )


@router.post("/cdc/hang-doi/import-batch", response_class=HTMLResponse)
async def import_batch(
    request: Request, queue_ids: list[int] = Form(default=[]), csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_IMPORT_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    if not queue_ids:
        return _redirect_to_list(request, err="Chưa chọn mục nào để nhập.")
    ok_count = 0
    errors: list[str] = []
    for qid in queue_ids:
        try:
            core.import_queue_item(qid, db_path=settings.db_path, actor=user.username)
            ok_count += 1
        except ValueError as exc:
            errors.append(f"#{qid}: {exc}")
    if errors:
        return _redirect_to_list(request, err=f"Đã nhập {ok_count}/{len(queue_ids)} mục. Lỗi: " + "; ".join(errors))
    return _redirect_to_list(request, msg=f"Đã nhập thành công {ok_count} mục.")


@router.post("/cdc/hang-doi/{queue_id}/delete", response_class=HTMLResponse)
async def delete_one(
    queue_id: int, request: Request, csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_DELETE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    try:
        core.delete_queue_item(queue_id, db_path=settings.db_path, actor=user.username)
    except ValueError as exc:
        return _redirect_to_list(request, err=str(exc))
    return _redirect_to_list(request, msg="Đã xoá mục khỏi hàng đợi.")
