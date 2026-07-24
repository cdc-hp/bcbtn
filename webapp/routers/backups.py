"""`/cdc/sao-luu` — Giai đoạn 6 (xem TASKS.md): sao lưu/phục hồi CSDL qua Web, tái dùng nguyên
`backup_manager` (đã dùng cho tính năng sao lưu tự động của máy trạm PyQt6). Xem/tạo bản sao lưu
= super_admin/admin; PHỤC HỒI (ghi đè toàn bộ CSDL đang chạy) chỉ super_admin — rủi ro cao hơn
hẳn các thao tác quản trị khác trong Web App này (chọn nhầm bản sao lưu cũ có thể mất dữ liệu mới
nhất), nên tách riêng mức quyền thay vì dùng chung CAN_MANAGE của `/cdc/tai-khoan`."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import backup_manager
import core
from webapp import TEMPLATES_DIR, auth
from webapp.config import WebAppSettings
from webapp.dependencies import ForbiddenError, get_settings_dep, require_role

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)

CAN_VIEW_ROLES = (core.CDC_ROLE_SUPER_ADMIN, core.CDC_ROLE_ADMIN)
CAN_RESTORE_ROLES = (core.CDC_ROLE_SUPER_ADMIN,)


def _redirect(msg: str = "", err: str = "") -> RedirectResponse:
    url = "/cdc/sao-luu"
    if msg:
        url += f"?msg={quote(msg)}"
    elif err:
        url += f"?err={quote(err)}"
    return RedirectResponse(url, status_code=303)


def _resolve_backup_path(name: str) -> Path:
    directory = backup_manager.backup_directory()
    candidate = (directory / name).resolve()
    if candidate.parent != directory or not candidate.exists():
        raise ForbiddenError("Không tìm thấy bản sao lưu.")
    return candidate


@router.get("/cdc/sao-luu", response_class=HTMLResponse)
def list_page(
    request: Request, msg: str = "", err: str = "",
    user: auth.CurrentUser = Depends(require_role(*CAN_VIEW_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    policy = backup_manager.load_policy()
    health = backup_manager.backup_health(policy)
    backups = backup_manager.list_backups(policy)
    token = auth.get_csrf_token(request)
    response = templates.TemplateResponse(request, "backups.html", {
        "user": user, "csrf_token": token, "active": "sao-luu",
        "policy": policy, "health": health, "backups": backups,
        "can_restore": user.has_role(*CAN_RESTORE_ROLES), "msg": msg, "err": err,
    })
    auth.set_csrf_cookie(response, request, token)
    return response


@router.post("/cdc/sao-luu/tao", response_class=HTMLResponse)
async def create_now(
    request: Request, csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_VIEW_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    try:
        path = core.create_backup(settings.db_path)
    except RuntimeError as exc:
        return _redirect(err=str(exc))
    core.log_audit("create_backup_web", actor=user.username, db_path=settings.db_path)
    return _redirect(msg=f"Đã tạo bản sao lưu: {path.name}")


@router.get("/cdc/sao-luu/{name}/tai-ve")
def download(
    name: str,
    user: auth.CurrentUser = Depends(require_role(*CAN_VIEW_ROLES)),
):
    path = _resolve_backup_path(name)
    return FileResponse(path, filename=path.name)


@router.post("/cdc/sao-luu/{name}/phuc-hoi", response_class=HTMLResponse)
async def restore(
    name: str, request: Request, csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_RESTORE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    path = _resolve_backup_path(name)
    try:
        result = backup_manager.restore_backup(path, settings.db_path)
    except (ValueError, RuntimeError) as exc:
        return _redirect(err=str(exc))
    core.log_audit(
        "restore_backup_web", actor=user.username,
        detail=f"restored_from={result['restored_from']}; safety_backup={result['safety_backup']}",
        db_path=settings.db_path,
    )
    return _redirect(msg=f"Đã phục hồi từ {path.name}. Bản sao lưu an toàn trước khi phục hồi: {result['safety_backup']}")


@router.post("/cdc/sao-luu/chinh-sach", response_class=HTMLResponse)
async def save_policy(
    request: Request, csrf_token: str = Form(""), enabled: int = Form(0), interval_hours: int = Form(24),
    keep_daily: int = Form(7), keep_weekly: int = Form(8), keep_monthly: int = Form(12),
    keep_manual: int = Form(20), verify_after_backup: int = Form(1),
    user: auth.CurrentUser = Depends(require_role(*CAN_RESTORE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    policy = backup_manager.load_policy()
    policy.enabled = bool(enabled)
    policy.interval_hours = interval_hours
    policy.keep_daily = keep_daily
    policy.keep_weekly = keep_weekly
    policy.keep_monthly = keep_monthly
    policy.keep_manual = keep_manual
    policy.verify_after_backup = bool(verify_after_backup)
    backup_manager.save_policy(policy)
    core.log_audit("save_backup_policy_web", actor=user.username, db_path=settings.db_path)
    return _redirect(msg="Đã lưu cấu hình sao lưu.")
