"""`/cdc/tai-khoan` — Giai đoạn 6 (xem TASKS.md): quản lý tài khoản quản trị viên qua Web, chỉ
`super_admin`. Tái dùng nguyên `core.create_cdc_account`/`list_cdc_accounts`/
`set_cdc_account_active`/`set_cdc_account_role`/`reset_cdc_account_password` — router chỉ thêm
1 lớp bảo vệ mà `core.py` chủ định KHÔNG tự kiểm tra (xem docstring `set_cdc_account_role`):
chặn super_admin tự khoá/tự hạ quyền chính mình, tránh tự đá mình ra khỏi hệ thống mà không còn
ai super_admin để mở lại."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import core
from webapp import auth
from webapp.config import WebAppSettings
from webapp.dependencies import ForbiddenError, get_settings_dep, require_role

router = APIRouter()
templates = Jinja2Templates(directory="webapp/templates")

CAN_MANAGE_ROLES = (core.CDC_ROLE_SUPER_ADMIN,)
ROLE_LABELS = {
    core.CDC_ROLE_SUPER_ADMIN: "Quản trị cấp cao", core.CDC_ROLE_ADMIN: "Quản trị viên",
    core.CDC_ROLE_DATA_OPERATOR: "Nhập liệu", core.CDC_ROLE_VIEWER: "Chỉ xem",
}


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def _redirect(msg: str = "", err: str = "") -> RedirectResponse:
    url = "/cdc/tai-khoan"
    if msg:
        url += f"?msg={quote(msg)}"
    elif err:
        url += f"?err={quote(err)}"
    return RedirectResponse(url, status_code=303)


@router.get("/cdc/tai-khoan", response_class=HTMLResponse)
def list_accounts(
    request: Request, msg: str = "", err: str = "",
    user: auth.CurrentUser = Depends(require_role(*CAN_MANAGE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    accounts = core.list_cdc_accounts(db_path=settings.db_path)
    for account in accounts:
        account["role_label"] = ROLE_LABELS.get(account["role"], account["role"])
        account["locked"] = bool(account["locked_until"] and account["locked_until"] > _now())
    token = auth.get_csrf_token(request)
    response = templates.TemplateResponse(request, "accounts.html", {
        "user": user, "csrf_token": token, "active": "tai-khoan",
        "accounts": accounts, "roles": core.CDC_ROLES, "role_labels": ROLE_LABELS, "msg": msg, "err": err,
    })
    auth.set_csrf_cookie(response, request, token)
    return response


@router.post("/cdc/tai-khoan/tao", response_class=HTMLResponse)
async def create_account(
    request: Request, username: str = Form(...), display_name: str = Form(""),
    role: str = Form(core.CDC_ROLE_ADMIN), password: str = Form(...), csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_MANAGE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    try:
        result = core.create_cdc_account(
            username, password, display_name=display_name, role=role,
            db_path=settings.db_path, actor=user.username,
        )
    except ValueError as exc:
        return _redirect(err=str(exc))
    return _redirect(msg=f"Đã tạo tài khoản {result['username']}.")


@router.post("/cdc/tai-khoan/{account_id}/kich-hoat", response_class=HTMLResponse)
async def toggle_active(
    account_id: int, request: Request, active: int = Form(...), csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_MANAGE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    if account_id == user.account_id and not active:
        return _redirect(err="Không thể tự khoá tài khoản của chính mình.")
    try:
        core.set_cdc_account_active(account_id, bool(active), db_path=settings.db_path, actor=user.username)
    except ValueError as exc:
        return _redirect(err=str(exc))
    return _redirect(msg="Đã cập nhật trạng thái tài khoản." if active else "Đã khoá tài khoản.")


@router.post("/cdc/tai-khoan/{account_id}/vai-tro", response_class=HTMLResponse)
async def change_role(
    account_id: int, request: Request, role: str = Form(...), csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_MANAGE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    if account_id == user.account_id and role != core.CDC_ROLE_SUPER_ADMIN:
        return _redirect(err="Không thể tự hạ vai trò của chính mình.")
    try:
        core.set_cdc_account_role(account_id, role, db_path=settings.db_path, actor=user.username)
    except ValueError as exc:
        return _redirect(err=str(exc))
    return _redirect(msg="Đã đổi vai trò tài khoản.")


@router.post("/cdc/tai-khoan/{account_id}/dat-lai-mat-khau", response_class=HTMLResponse)
async def reset_password(
    account_id: int, request: Request, new_password: str = Form(...), csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_MANAGE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    try:
        core.reset_cdc_account_password(account_id, new_password, db_path=settings.db_path, actor=user.username)
    except ValueError as exc:
        return _redirect(err=str(exc))
    return _redirect(msg="Đã đặt lại mật khẩu — người dùng phải đổi mật khẩu ở lần đăng nhập tới.")
