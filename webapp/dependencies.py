"""FastAPI Depends() dùng chung cho các router — xác thực, phân quyền, CSRF, kiểm tra đã cấu
hình lần đầu chưa. Đặt logic phân quyền tập trung ở đây (không rải rác trong từng route) để dễ
soát lại toàn bộ quy tắc truy cập một chỗ."""

from __future__ import annotations

from fastapi import Depends, Form, Request

import core
from webapp import auth
from webapp.config import WebAppSettings, get_settings


class RedirectException(Exception):
    """Dependency muốn chuyển hướng thay vì trả lỗi (chưa đăng nhập, chưa cấu hình lần đầu,
    bắt buộc đổi mật khẩu...) — main.py đăng ký exception handler chuyển thành 303 redirect."""

    def __init__(self, location: str) -> None:
        self.location = location


class ForbiddenError(Exception):
    """Đã đăng nhập nhưng vai trò không đủ quyền — khác chưa đăng nhập (không redirect về
    login, hiển thị thẳng trang 403)."""


def get_settings_dep() -> WebAppSettings:
    return get_settings()


def require_setup_done(settings: WebAppSettings = Depends(get_settings_dep)) -> WebAppSettings:
    if not core.has_cdc_accounts(db_path=settings.db_path):
        raise RedirectException("/cdc/setup")
    return settings


def get_current_user(
    request: Request, settings: WebAppSettings = Depends(get_settings_dep),
) -> auth.CurrentUser | None:
    return auth.get_current_user(request, settings)


def require_login(
    request: Request,
    user: auth.CurrentUser | None = Depends(get_current_user),
    _setup: WebAppSettings = Depends(require_setup_done),
) -> auth.CurrentUser:
    if not user:
        raise RedirectException("/cdc/login?next=" + request.url.path)
    return user


def require_password_current(user: auth.CurrentUser = Depends(require_login)) -> auth.CurrentUser:
    """Dùng cho MỌI route trừ /cdc/login, /cdc/change-password, /cdc/logout — chặn thao tác gì
    khác cho tới khi đổi xong mật khẩu tạm/bị đặt lại (Section 6, "buộc đổi mật khẩu lần đầu")."""
    if user.must_change_password:
        raise RedirectException("/cdc/change-password")
    return user


def require_role(*roles: str):
    """Factory tạo dependency kiểm tra vai trò — dùng: Depends(require_role(core.CDC_ROLE_SUPER_ADMIN))."""

    def _check(user: auth.CurrentUser = Depends(require_password_current)) -> auth.CurrentUser:
        if not user.has_role(*roles):
            raise ForbiddenError(f"Vai trò '{user.role}' không có quyền truy cập trang này.")
        return user

    return _check


async def verify_csrf_form(request: Request, csrf_token: str = Form(default="")) -> None:
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF). Tải lại trang và thử lại.")
