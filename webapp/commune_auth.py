"""Phiên đăng nhập tài khoản xã — tách riêng khỏi `webapp/auth.py` (tài khoản CDC) vì đây là 1
ranh giới quyền hoàn toàn khác: tài khoản xã chỉ được xem dữ liệu đúng xã mình, không được lẫn với
phiên quản trị viên CDC dù chỉ 1 chút. Cấu trúc mirror `webapp/auth.py` nhưng ký/đọc bằng
`core.issue_commune_token`/`verify_commune_token` (đã có sẵn, khác payload với
`issue_admin_token`/`verify_admin_token`). CSRF dùng lại nguyên `webapp/auth.py` (double-submit
cookie không phụ thuộc loại phiên nào)."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request, Response

import core
from webapp.config import COMMUNE_SESSION_COOKIE_NAME, COMMUNE_SESSION_TTL_SECONDS, WebAppSettings


@dataclass
class CommuneCurrentUser:
    account_id: int
    commune: str
    username: str
    display_name: str


def _is_https_request(request: Request) -> bool:
    """Cloudflare Tunnel chuyển tiếp vào localhost bằng HTTP thuần và gắn X-Forwarded-Proto —
    xem giải thích đầy đủ ở `webapp/auth.py::_is_https_request` (bản gốc)."""
    forwarded = request.headers.get("x-forwarded-proto", "").lower()
    return forwarded == "https" or request.url.scheme == "https"


def create_commune_session_cookie(response: Response, request: Request, account: dict, settings: WebAppSettings) -> None:
    token = core.issue_commune_token(
        account["id"], account["commune"], account["username"], settings.session_secret,
        ttl_seconds=COMMUNE_SESSION_TTL_SECONDS,
    )
    response.set_cookie(
        COMMUNE_SESSION_COOKIE_NAME, token, max_age=COMMUNE_SESSION_TTL_SECONDS, httponly=True,
        secure=_is_https_request(request), samesite="lax", path="/",
    )


def clear_commune_session_cookie(response: Response) -> None:
    response.delete_cookie(COMMUNE_SESSION_COOKIE_NAME, path="/")


def get_current_commune_user(request: Request, settings: WebAppSettings) -> CommuneCurrentUser | None:
    """Đọc cookie phiên xã, xác minh chữ ký + hạn dùng, rồi tra CSDL lấy trạng thái MỚI NHẤT
    (tài khoản bị khoá có hiệu lực ngay, không phải đợi token cũ hết hạn)."""
    token = request.cookies.get(COMMUNE_SESSION_COOKIE_NAME, "")
    payload = core.verify_commune_token(token, settings.session_secret)
    if not payload:
        return None
    accounts = core.list_commune_accounts(db_path=settings.db_path)
    row = next((a for a in accounts if a["id"] == payload["account_id"]), None)
    if not row or not row["active"]:
        return None
    return CommuneCurrentUser(
        account_id=row["id"], commune=row["commune"], username=row["username"],
        display_name=row["display_name"] or row["commune"],
    )
