"""Máy chủ dự phòng (failover thủ công) — xem CLAUDE.md mục "Máy chủ dự phòng" và `ha_sync.py`.

`/noi-bo/ha/*`: gọi máy-tới-máy, xác thực bằng khoá `peer_shared_key` (header `X-CDC-Peer-Key`,
KHÔNG qua session — giống mẫu `webapp/routers/submission_api.py`). Máy dự phòng đặt ở nơi khác
(khác điện/mạng với máy chính, xem CLAUDE.md) nên các endpoint này công khai ra Internet qua tên
miền Cloudflare Tunnel RIÊNG của từng máy (khác `cdc-hp.io.vn` dùng chung) — có giới hạn tần suất
(`ha_peer_limiter`) chống dò khoá, ngoài xác thực bằng khoá.

`/cdc/vai-tro-may-chu/*`: hành động của super-admin (session + CSRF), giống mẫu
`webapp/routers/settings.py`."""

from __future__ import annotations

import hmac
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.background import BackgroundTask

import backup_manager
import core
import deployment_config
import ha_sync
from webapp import auth
from webapp.dependencies import ForbiddenError, get_settings_dep, require_role
from webapp.config import WebAppSettings
from webapp.services.http import client_ip
from webapp.services.rate_limit import ha_peer_limiter

router = APIRouter()

CAN_MANAGE_ROLE = (core.CDC_ROLE_SUPER_ADMIN,)


def _constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status)


def _redirect(msg: str = "", err: str = "") -> RedirectResponse:
    url = "/cdc/cau-hinh"
    if msg:
        url += f"?msg={quote(msg)}"
    elif err:
        url += f"?err={quote(err)}"
    return RedirectResponse(url, status_code=303)


# --- Máy-tới-máy --------------------------------------------------------------------------

@router.get("/noi-bo/ha/snapshot")
def snapshot(request: Request, settings: WebAppSettings = Depends(get_settings_dep)):
    if not ha_peer_limiter.allow(client_ip(request)):
        return _error(429, "Gửi quá nhiều lần trong thời gian ngắn, thử lại sau vài phút.")
    if not settings.config.peer_shared_key:
        return _error(503, "Máy chủ chưa cấu hình khoá máy-tới-máy (peer_shared_key).")
    provided_key = request.headers.get("x-cdc-peer-key", "")
    if not _constant_time_equals(provided_key, settings.config.peer_shared_key):
        return _error(401, "Sai khoá máy-tới-máy.")
    if settings.config.server_role != "primary":
        return _error(409, "Máy này hiện không phải máy chính — không phát snapshot.")

    snapshot_path = backup_manager.create_backup(
        settings.db_path, kind="ha_snapshot", update_schedule=False,
    )
    return FileResponse(
        snapshot_path, media_type="application/octet-stream", filename="ha_snapshot.db",
        background=BackgroundTask(snapshot_path.unlink, missing_ok=True),
    )


@router.post("/noi-bo/ha/demote")
def demote(request: Request, settings: WebAppSettings = Depends(get_settings_dep)):
    if not ha_peer_limiter.allow(client_ip(request)):
        return _error(429, "Gửi quá nhiều lần trong thời gian ngắn, thử lại sau vài phút.")
    if not settings.config.peer_shared_key:
        return _error(503, "Máy chủ chưa cấu hình khoá máy-tới-máy (peer_shared_key).")
    provided_key = request.headers.get("x-cdc-peer-key", "")
    if not _constant_time_equals(provided_key, settings.config.peer_shared_key):
        return _error(401, "Sai khoá máy-tới-máy.")

    config = settings.config
    config.server_role = "standby"
    deployment_config.save_config(config)
    core.log_audit("ha_demoted_by_peer", actor="he_thong", db_path=settings.db_path)
    ha_sync.reconcile_public_tunnel_service("standby", db_path=settings.db_path)
    return JSONResponse({"ok": True})


@router.post("/noi-bo/ha/yeu-cau-dong-bo")
def request_sync(request: Request, settings: WebAppSettings = Depends(get_settings_dep)):
    """Máy chính gọi sang để nhờ máy này (nếu đúng đang là dự phòng) tự kéo snapshot NGAY — xem
    nút "Yêu cầu máy dự phòng đồng bộ ngay" trong `/cdc/vai-tro-may-chu/yeu-cau-may-kia-dong-bo`."""
    if not ha_peer_limiter.allow(client_ip(request)):
        return _error(429, "Gửi quá nhiều lần trong thời gian ngắn, thử lại sau vài phút.")
    if not settings.config.peer_shared_key:
        return _error(503, "Máy chủ chưa cấu hình khoá máy-tới-máy (peer_shared_key).")
    provided_key = request.headers.get("x-cdc-peer-key", "")
    if not _constant_time_equals(provided_key, settings.config.peer_shared_key):
        return _error(401, "Sai khoá máy-tới-máy.")
    if settings.config.server_role != "standby":
        return _error(409, "Máy này hiện không phải máy dự phòng — không có gì để kéo.")

    result = ha_sync.run_standby_pull_once(db_path=settings.db_path)
    if result.get("skipped"):
        return JSONResponse({"ok": False, "error": result["reason"]})
    if result.get("error"):
        return JSONResponse({"ok": False, "error": result["error"]})
    return JSONResponse({"ok": True, "result": result})


@router.get("/noi-bo/ha/vai-tro")
def role_status(request: Request, settings: WebAppSettings = Depends(get_settings_dep)):
    """Cho máy kia hỏi vai trò hiện tại — dùng bởi `ha_sync.resolve_startup_conflict` lúc khởi
    động để phát hiện xung đột "song chính" (xem CLAUDE.md mục "Máy chủ dự phòng")."""
    if not ha_peer_limiter.allow(client_ip(request)):
        return _error(429, "Gửi quá nhiều lần trong thời gian ngắn, thử lại sau vài phút.")
    if not settings.config.peer_shared_key:
        return _error(503, "Máy chủ chưa cấu hình khoá máy-tới-máy (peer_shared_key).")
    provided_key = request.headers.get("x-cdc-peer-key", "")
    if not _constant_time_equals(provided_key, settings.config.peer_shared_key):
        return _error(401, "Sai khoá máy-tới-máy.")
    return JSONResponse({"server_role": settings.config.server_role})


# --- Super-admin ---------------------------------------------------------------------------

@router.post("/cdc/vai-tro-may-chu/thang-cap")
def promote(
    request: Request, csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_MANAGE_ROLE)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    config = settings.config

    # Kéo bù 1 lần cuối TRƯỚC khi đổi vai trò, trong lúc còn là dự phòng (tự no-op nếu máy này
    # hiện không phải dự phòng) — cố lấy dữ liệu mới nhất có thể từ máy kia trước khi tự nhận ghi
    # dữ liệu. Cố gắng hết sức, KHÔNG chặn việc thăng cấp nếu bước này lỗi (máy kia có thể chính
    # là máy đang không phản hồi được — lý do phải thăng cấp máy này lên).
    catch_up = ha_sync.run_standby_pull_once(db_path=settings.db_path)

    config.server_role = "primary"
    deployment_config.save_config(config)
    ha_sync.reconcile_public_tunnel_service("primary", db_path=settings.db_path)

    peer_notified = False
    if config.peer_server_url and config.peer_shared_key:
        peer_notified = ha_sync.notify_peer_demote(config.peer_server_url, config.peer_shared_key)

    catch_up_summary = (
        "ok" if "restored_from" in catch_up
        else catch_up.get("reason") or catch_up.get("error") or "khong_ro"
    )
    core.log_audit(
        "promote_to_primary", actor=user.username,
        detail=f"peer_notified={peer_notified}; catch_up={catch_up_summary}", db_path=settings.db_path,
    )
    if peer_notified:
        return _redirect(msg="Đã đặt máy này làm máy chính. Máy kia đã tự chuyển sang dự phòng.")
    if config.peer_server_url:
        return _redirect(
            err="Đã đặt máy này làm máy chính, NHƯNG không báo được máy kia tự hạ cấp — "
            "vào máy kia và bấm \"Đặt máy này làm máy dự phòng\" ngay để tránh xung đột dữ liệu."
        )
    return _redirect(msg="Đã đặt máy này làm máy chính.")


@router.post("/cdc/vai-tro-may-chu/xuong-cap")
def demote_self(
    request: Request, csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_MANAGE_ROLE)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    config = settings.config
    config.server_role = "standby"
    deployment_config.save_config(config)
    core.log_audit("demote_to_standby", actor=user.username, db_path=settings.db_path)
    ha_sync.reconcile_public_tunnel_service("standby", db_path=settings.db_path)
    return _redirect(msg="Đã đặt máy này làm máy dự phòng — ngừng nhận thay đổi dữ liệu.")


@router.post("/cdc/vai-tro-may-chu/dong-bo-ngay")
def sync_now(
    request: Request, csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_MANAGE_ROLE)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    result = ha_sync.run_standby_pull_once(db_path=settings.db_path)
    if result.get("skipped"):
        return _redirect(err=result["reason"])
    if result.get("error"):
        return _redirect(err=f"Đồng bộ lỗi: {result['error']}")
    return _redirect(msg="Đã đồng bộ xong từ máy chính.")


@router.post("/cdc/vai-tro-may-chu/yeu-cau-may-kia-dong-bo")
def request_peer_sync(
    request: Request, csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_MANAGE_ROLE)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    """Máy CHÍNH chủ động nhờ máy dự phòng tự kéo snapshot ngay (thay vì đợi chu kỳ định kỳ của
    máy đó) — vd trước khi tắt máy chính để bảo trì. Chiều đồng bộ vẫn không đổi: máy dự phòng tự
    kéo, máy chính chỉ gọi sang NHỜ nó kéo sớm hơn."""
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    config = settings.config
    if not (config.peer_server_url and config.peer_shared_key):
        return _redirect(err="Chưa cấu hình địa chỉ/khoá máy kia.")
    result = ha_sync.request_peer_sync_now(config.peer_server_url, config.peer_shared_key)
    core.log_audit(
        "ha_request_peer_sync", actor=user.username,
        detail=f"ok={result.get('ok')}; error={result.get('error', '')}", db_path=settings.db_path,
    )
    if result.get("ok"):
        return _redirect(msg="Đã yêu cầu máy dự phòng đồng bộ — máy đó đã kéo xong.")
    return _redirect(err=f"Yêu cầu máy dự phòng đồng bộ thất bại: {result.get('error', 'không rõ lỗi')}")


@router.get("/cdc/vai-tro-may-chu/trang-thai", response_class=JSONResponse)
def status(
    _user: auth.CurrentUser = Depends(require_role(*CAN_MANAGE_ROLE)),
):
    return JSONResponse(ha_sync.get_status(), headers={"Cache-Control": "no-store"})
