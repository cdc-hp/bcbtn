"""Placeholder — Dashboard đầy đủ (số liệu ca bệnh/ổ dịch, hàng đợi, tình hình nộp theo xã,
sao lưu gần nhất, đồng bộ máy chủ phụ...) thuộc Giai đoạn 4, xem TASKS.md mục 6. Route này chỉ
tồn tại để có nơi chuyển hướng tới sau khi đăng nhập thành công trong Giai đoạn 2."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from webapp import auth
from webapp.dependencies import require_password_current

router = APIRouter()
templates = Jinja2Templates(directory="webapp/templates")


@router.get("/cdc/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user: auth.CurrentUser = Depends(require_password_current)):
    token = auth.get_csrf_token(request)
    response = templates.TemplateResponse(request, "dashboard_placeholder.html", {"user": user, "csrf_token": token})
    auth.set_csrf_cookie(response, request, token)
    return response
