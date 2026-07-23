"""Phiên đăng nhập + CSRF cho Web App.

Phiên đăng nhập tái dùng `core.issue_admin_token`/`verify_admin_token` đã có sẵn (ký HMAC,
stateless, cùng cơ chế với `issue_commune_token`) thay vì thêm thư viện session mới — chỉ khác
chỗ lưu: trước đây token nằm trong header `X-GSBTN-Admin-Token` (máy trạm PyQt6), giờ nằm trong
cookie HttpOnly để trình duyệt tự gửi kèm mỗi request.

CSRF dùng mẫu "double-submit cookie": 1 cookie ngẫu nhiên không HttpOnly (để form đọc và nhúng
lại) + form phải gửi kèm đúng giá trị đó. Không cần bảng session hay thư viện thêm — kẻ tấn công
CSRF không đọc được cookie của nạn nhân do same-origin policy nên không thể đoán đúng giá trị.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from fastapi import Request, Response

import core
from webapp.config import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, SESSION_TTL_SECONDS, WebAppSettings


@dataclass
class CurrentUser:
    account_id: int
    username: str
    display_name: str
    role: str
    must_change_password: bool

    def has_role(self, *roles: str) -> bool:
        return self.role in roles


def _is_https_request(request: Request) -> bool:
    """Cloudflare Tunnel chuyển tiếp vào localhost bằng HTTP thuần và gắn X-Forwarded-Proto —
    bản thân Uvicorn không thấy TLS trực tiếp nên phải đọc header này để quyết định cookie
    Secure. Truy cập trực tiếp 127.0.0.1 (dev/LAN) không có header này -> coi là HTTP."""
    forwarded = request.headers.get("x-forwarded-proto", "").lower()
    return forwarded == "https" or request.url.scheme == "https"


def create_session_cookie(response: Response, request: Request, account: dict, settings: WebAppSettings) -> None:
    token = core.issue_admin_token(
        account["id"], account["username"], settings.session_secret, ttl_seconds=SESSION_TTL_SECONDS
    )
    response.set_cookie(
        SESSION_COOKIE_NAME, token, max_age=SESSION_TTL_SECONDS, httponly=True,
        secure=_is_https_request(request), samesite="lax", path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


def get_current_user(request: Request, settings: WebAppSettings) -> CurrentUser | None:
    """Đọc cookie phiên, xác minh chữ ký + hạn dùng, rồi tra CSDL lấy trạng thái MỚI NHẤT (vai
    trò/khoá tài khoản có hiệu lực ngay, không phải đợi token cũ hết hạn mới cập nhật)."""
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    payload = core.verify_admin_token(token, settings.session_secret)
    if not payload:
        return None
    accounts = core.list_cdc_accounts(db_path=settings.db_path)
    row = next((a for a in accounts if a["id"] == payload["account_id"]), None)
    if not row or not row["active"]:
        return None
    return CurrentUser(
        account_id=row["id"], username=row["username"], display_name=row["display_name"] or row["username"],
        role=row["role"] or core.CDC_ROLE_ADMIN, must_change_password=bool(row["must_change_password"]),
    )


def get_csrf_token(request: Request) -> str:
    """Giá trị CSRF hiện tại (giữ nguyên nếu cookie đã có — người dùng có thể mở nhiều tab/form
    cùng lúc) hoặc sinh mới nếu chưa có. Hàm thuần, không đụng tới response — gọi TRƯỚC khi
    dựng TemplateResponse để nhúng được giá trị vào HTML ngay từ lần render đầu."""
    return request.cookies.get(CSRF_COOKIE_NAME, "") or secrets.token_urlsafe(32)


def set_csrf_cookie(response: Response, request: Request, token: str) -> None:
    """Ghi cookie CSRF lên response — gọi SAU khi đã dựng TemplateResponse với đúng `token` ở
    trên trong context. Không HttpOnly (double-submit cookie chỉ cần JS/form đọc lại được)."""
    response.set_cookie(
        CSRF_COOKIE_NAME, token, httponly=False, samesite="lax", path="/", secure=_is_https_request(request),
    )


def verify_csrf(request: Request, submitted_token: str) -> bool:
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
    return bool(cookie_token) and secrets.compare_digest(cookie_token, submitted_token or "")
