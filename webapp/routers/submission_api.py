"""POST /queue/submit — nhận báo cáo từ Google Apps Script, tương thích với request hiện tại
của `Code.gs: tryForwardToMainServer` (không đổi phía Code.gs). Xem TASKS.md Giai đoạn 3 và
Section 7 của nhiệm vụ chuyển sang Web App."""

from __future__ import annotations

import base64
import binascii
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import core
from webapp.config import get_settings
from webapp.services.http import client_ip
from webapp.services.rate_limit import queue_submit_limiter

router = APIRouter()

MAX_REQUEST_BYTES = 110 * 1024 * 1024


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status)


@router.post("/queue/submit")
async def submit(request: Request):
    settings = get_settings()

    content_length = request.headers.get("content-length", "")
    if content_length.isdigit() and int(content_length) > MAX_REQUEST_BYTES:
        return _error(413, "Yêu cầu vượt giới hạn 110 MB.")

    if not settings.config.gas_api_key:
        return _error(503, "Máy chủ chưa cấu hình khoá API cho Google Apps Script (gas_api_key).")
    provided_key = request.headers.get("x-gsbtn-password", "")
    if provided_key != settings.config.gas_api_key:
        return _error(401, "Sai khoá API.")

    body = await request.body()
    if len(body) > MAX_REQUEST_BYTES:
        return _error(413, "Yêu cầu vượt giới hạn 110 MB.")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _error(400, "Nội dung yêu cầu không phải JSON hợp lệ.")
    if not isinstance(payload, dict):
        return _error(400, "Nội dung yêu cầu không hợp lệ.")

    commune = str(payload.get("commune", ""))
    week = str(payload.get("week", ""))
    rate_key = f"{client_ip(request)}:{commune[:80]}"
    if not queue_submit_limiter.allow(rate_key):
        return _error(429, "Gửi quá nhiều lần trong thời gian ngắn, thử lại sau vài phút.")

    content_b64 = payload.get("content_base64")
    if not isinstance(content_b64, str) or not content_b64:
        return _error(400, "Thiếu nội dung file Excel.")
    try:
        file_bytes = base64.b64decode(content_b64.encode("ascii"), validate=True)
    except (ValueError, binascii.Error):
        return _error(400, "Nội dung file không phải base64 hợp lệ.")

    try:
        result = core.queue_submit(
            commune, week, str(payload.get("file_name", "du_lieu.xlsx")), file_bytes,
            source="server_chinh", submitted_by=str(payload.get("submitted_by", "")),
            db_path=settings.db_path,
        )
    except ValueError as exc:
        core.log_audit(
            "queue_submit_rejected", actor="gas", commune=commune, detail=str(exc),
            ip=client_ip(request), db_path=settings.db_path,
        )
        return _error(400, str(exc))

    return JSONResponse({"ok": True, "result": result})
