"""Đăng nhập/đăng xuất tài khoản xã (`/xa/dang-nhap`, `/xa/dang-xuat`) — tách hẳn khỏi
`/cdc/login` (tài khoản CDC), dùng `webapp/commune_auth.py` (phiên riêng, cookie riêng). Xem
CLAUDE.md mục "Tài khoản xã"."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import core
from webapp import TEMPLATES_DIR, auth, commune_auth
from webapp.config import WebAppSettings
from webapp.dependencies import get_current_commune_user, get_settings_dep

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def _render(request: Request, template: str, context: dict) -> HTMLResponse:
    token = auth.get_csrf_token(request)
    response = templates.TemplateResponse(request, template, {**context, "csrf_token": token})
    auth.set_csrf_cookie(response, request, token)
    return response


@router.get("/xa/dang-nhap", response_class=HTMLResponse)
def login_form(
    request: Request, next: str = "/xa/ca-benh",
    user: commune_auth.CommuneCurrentUser | None = Depends(get_current_commune_user),
):
    if user:
        return RedirectResponse(next or "/xa/ca-benh", status_code=303)
    return _render(request, "xa_login.html", {"next_url": next})


@router.post("/xa/dang-nhap", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/xa/ca-benh"),
    csrf_token: str = Form(""),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    ctx = {"username": username, "next_url": next}
    if not auth.verify_csrf(request, csrf_token):
        return _render(request, "xa_login.html", {**ctx, "error": "Phiên làm việc đã hết hạn, tải lại trang và thử lại."})

    account = core.verify_commune_account(username, password, db_path=settings.db_path)
    if not account:
        return _render(request, "xa_login.html", {**ctx, "error": "Sai tên đăng nhập hoặc mật khẩu."})

    response = RedirectResponse(next or "/xa/ca-benh", status_code=303)
    commune_auth.create_commune_session_cookie(response, request, account, settings)
    return response


@router.post("/xa/dang-xuat")
def logout():
    response = RedirectResponse("/xa/dang-nhap", status_code=303)
    commune_auth.clear_commune_session_cookie(response)
    return response
