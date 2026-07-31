"""`/cdc/tai-khoan-xa` — quản lý tài khoản xã (khác hẳn `/cdc/tai-khoan` quản lý tài khoản CDC),
chỉ `super_admin`. Tái dùng nguyên `core.create_commune_account`/`list_commune_accounts`/
`set_commune_account_active`/`reset_commune_account_password`/`import_commune_accounts` — router
chỉ lo phần HTTP/CSRF/flash message, theo đúng khuôn `webapp/routers/accounts.py`."""

from __future__ import annotations

from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import core
from webapp import TEMPLATES_DIR, auth
from webapp.config import WebAppSettings
from webapp.dependencies import ForbiddenError, get_settings_dep, require_role
from webapp.services.pagination import paginate

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)

CAN_MANAGE_ROLES = (core.CDC_ROLE_SUPER_ADMIN,)


def _redirect(msg: str = "", err: str = "") -> RedirectResponse:
    url = "/cdc/tai-khoan-xa"
    if msg:
        url += f"?msg={quote(msg)}"
    elif err:
        url += f"?err={quote(err)}"
    return RedirectResponse(url, status_code=303)


@router.get("/cdc/tai-khoan-xa", response_class=HTMLResponse)
def list_commune_accounts(
    request: Request, msg: str = "", err: str = "", page: int = 1,
    user: auth.CurrentUser = Depends(require_role(*CAN_MANAGE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    accounts = core.list_commune_accounts(db_path=settings.db_path)
    page_accounts, page_info = paginate(accounts, page)
    token = auth.get_csrf_token(request)
    response = templates.TemplateResponse(request, "commune_accounts.html", {
        "user": user, "csrf_token": token, "active": "tai-khoan-xa",
        "accounts": page_accounts, "total": page_info["total"],
        "page": page_info["page"], "total_pages": page_info["total_pages"],
        "pagination_base": "/cdc/tai-khoan-xa?page=",
        "official_communes": sorted(core.OFFICIAL_COMMUNES),
        "msg": msg, "err": err,
    })
    auth.set_csrf_cookie(response, request, token)
    return response


@router.post("/cdc/tai-khoan-xa/tao", response_class=HTMLResponse)
async def create_commune_account(
    request: Request, commune: str = Form(...), username: str = Form(...),
    display_name: str = Form(""), password: str = Form(...), csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_MANAGE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    if commune not in core.OFFICIAL_COMMUNES:
        return _redirect(err=f'"{commune}" không thuộc danh sách xã/phường chính thức.')
    try:
        result = core.create_commune_account(
            commune, username, password, display_name=display_name,
            db_path=settings.db_path, actor=user.username,
        )
    except ValueError as exc:
        return _redirect(err=str(exc))
    return _redirect(msg=f"Đã tạo tài khoản xã {result['commune']} ({result['username']}).")


@router.post("/cdc/tai-khoan-xa/nhap-excel", response_class=HTMLResponse)
async def import_commune_accounts_excel(
    request: Request, file: UploadFile = File(...), csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_MANAGE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    content = await file.read()
    try:
        summary = core.import_commune_accounts(BytesIO(content), db_path=settings.db_path, actor=user.username)
    except ValueError as exc:
        return _redirect(err=str(exc))
    except Exception:
        return _redirect(err="Không đọc được file — kiểm tra lại đây có đúng là file Excel (.xlsx) không.")
    text = summary.as_text()
    if summary.errors:
        text += " " + " | ".join(summary.errors[:15])
        if len(summary.errors) > 15:
            text += f" (và {len(summary.errors) - 15} lỗi khác)"
    if summary.created > 0:
        return _redirect(msg=text)
    return _redirect(err=text)


@router.post("/cdc/tai-khoan-xa/{account_id}/kich-hoat", response_class=HTMLResponse)
async def toggle_active(
    account_id: int, request: Request, active: int = Form(...), csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_MANAGE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    try:
        core.set_commune_account_active(account_id, bool(active), db_path=settings.db_path, actor=user.username)
    except ValueError as exc:
        return _redirect(err=str(exc))
    return _redirect(msg="Đã cập nhật trạng thái tài khoản." if active else "Đã khoá tài khoản.")


@router.post("/cdc/tai-khoan-xa/{account_id}/dat-lai-mat-khau", response_class=HTMLResponse)
async def reset_password(
    account_id: int, request: Request, new_password: str = Form(...), csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_MANAGE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    try:
        core.reset_commune_account_password(account_id, new_password, db_path=settings.db_path, actor=user.username)
    except ValueError as exc:
        return _redirect(err=str(exc))
    return _redirect(msg="Đã đặt lại mật khẩu tài khoản xã.")
