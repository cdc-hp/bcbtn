"""Đăng nhập, thiết lập lần đầu (tạo super_admin), đổi mật khẩu, đăng xuất — Section 6 (`/cdc/login`)
và Section 12 (cấu hình lần đầu) của nhiệm vụ chuyển sang Web App, xem TASKS.md."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import core
from webapp import auth
from webapp.config import WebAppSettings
from webapp.dependencies import ForbiddenError, get_current_user, get_settings_dep, require_login, require_setup_done

router = APIRouter()
templates = Jinja2Templates(directory="webapp/templates")


def client_ip(request: Request) -> str:
    """Ưu tiên IP thật của client khi phía trước có Cloudflare Tunnel/reverse proxy (header do
    hạ tầng đó gắn, không phải client tự khai nên không giả mạo được từ trình duyệt) — chỉ
    dùng request.client.host (IP kết nối TCP trực tiếp) khi truy cập thẳng qua LAN."""
    cf_ip = request.headers.get("cf-connecting-ip", "").strip()
    if cf_ip:
        return cf_ip
    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else ""


def _render(request: Request, template: str, context: dict) -> HTMLResponse:
    """Dựng TemplateResponse kèm cookie CSRF đúng với token vừa nhúng vào HTML — dùng chung
    cho mọi trang GET/lỗi form của router này thay vì lặp lại 3 dòng ở từng route."""
    token = auth.get_csrf_token(request)
    response = templates.TemplateResponse(request, template, {**context, "csrf_token": token})
    auth.set_csrf_cookie(response, request, token)
    return response


@router.get("/cdc/setup", response_class=HTMLResponse)
def setup_form(request: Request, settings: WebAppSettings = Depends(get_settings_dep)):
    if core.has_cdc_accounts(db_path=settings.db_path):
        return RedirectResponse("/cdc/login", status_code=303)
    return _render(request, "setup.html", {})


@router.post("/cdc/setup", response_class=HTMLResponse)
async def setup_submit(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(""),
    password: str = Form(...),
    password_confirm: str = Form(...),
    csrf_token: str = Form(""),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if core.has_cdc_accounts(db_path=settings.db_path):
        return RedirectResponse("/cdc/login", status_code=303)
    ctx = {"username": username, "display_name": display_name}
    if not auth.verify_csrf(request, csrf_token):
        return _render(request, "setup.html", {**ctx, "error": "Phiên làm việc đã hết hạn, tải lại trang và thử lại."})
    if password != password_confirm:
        return _render(request, "setup.html", {**ctx, "error": "Mật khẩu nhập lại không khớp."})
    try:
        core.create_cdc_account(
            username, password, display_name, role=core.CDC_ROLE_SUPER_ADMIN,
            must_change_password=False, db_path=settings.db_path, actor="thiet_lap_lan_dau",
        )
    except ValueError as exc:
        return _render(request, "setup.html", {**ctx, "error": str(exc)})
    return RedirectResponse("/cdc/login", status_code=303)


@router.get("/cdc/login", response_class=HTMLResponse)
def login_form(
    request: Request, next: str = "/cdc/dashboard",
    settings: WebAppSettings = Depends(require_setup_done),
    user: auth.CurrentUser | None = Depends(get_current_user),
):
    if user:
        return RedirectResponse(next or "/cdc/dashboard", status_code=303)
    return _render(request, "login.html", {"next_url": next, "version": core.VERSION})


@router.post("/cdc/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/cdc/dashboard"),
    csrf_token: str = Form(""),
    settings: WebAppSettings = Depends(require_setup_done),
):
    ctx = {"username": username, "next_url": next, "version": core.VERSION}
    if not auth.verify_csrf(request, csrf_token):
        return _render(request, "login.html", {**ctx, "error": "Phiên làm việc đã hết hạn, tải lại trang và thử lại."})

    lock_status = core.get_cdc_account_lock_status(username, db_path=settings.db_path)
    if lock_status:
        return _render(request, "login.html", {
            **ctx, "error": f"Tài khoản tạm khoá do đăng nhập sai nhiều lần. Thử lại sau {core.ACCOUNT_LOCKOUT_MINUTES} phút.",
        })

    account = core.verify_cdc_account(username, password, db_path=settings.db_path, ip=client_ip(request))
    if not account:
        return _render(request, "login.html", {**ctx, "error": "Sai tên đăng nhập hoặc mật khẩu."})

    destination = "/cdc/change-password" if account["must_change_password"] else (next or "/cdc/dashboard")
    response = RedirectResponse(destination, status_code=303)
    auth.create_session_cookie(response, request, account, settings)
    return response


@router.get("/cdc/change-password", response_class=HTMLResponse)
def change_password_form(request: Request, user: auth.CurrentUser = Depends(require_login)):
    return _render(request, "change_password.html", {"forced": user.must_change_password})


@router.post("/cdc/change-password", response_class=HTMLResponse)
async def change_password_submit(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    new_password_confirm: str = Form(...),
    csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_login),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    ctx = {"forced": user.must_change_password}
    if not auth.verify_csrf(request, csrf_token):
        return _render(request, "change_password.html", {**ctx, "error": "Phiên làm việc đã hết hạn, tải lại trang và thử lại."})
    if new_password != new_password_confirm:
        return _render(request, "change_password.html", {**ctx, "error": "Mật khẩu mới nhập lại không khớp."})
    try:
        core.change_cdc_account_password(user.account_id, current_password, new_password, db_path=settings.db_path)
    except ValueError as exc:
        return _render(request, "change_password.html", {**ctx, "error": str(exc)})
    return RedirectResponse("/cdc/dashboard", status_code=303)


@router.post("/cdc/logout")
async def logout(
    request: Request,
    csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_login),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    response = RedirectResponse("/cdc/login", status_code=303)
    auth.clear_session_cookie(response)
    core.log_audit("logout", actor=user.username, ip=client_ip(request), db_path=settings.db_path)
    return response
