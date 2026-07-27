"""POST /queue/submit — nhận báo cáo từ Google Apps Script, tương thích với request hiện tại
của `Code.gs: tryForwardToMainServer` (không đổi phía Code.gs). Xem TASKS.md Giai đoạn 3 và
Section 7 của nhiệm vụ chuyển sang Web App.

POST /queue/submit-xa — nhận báo cáo TRỰC TIẾP từ trình duyệt của xã, khi trang GitHub Pages
(`docs/index.html`) gọi thẳng máy chủ chính thay vì đi vòng qua Google Apps Script. Khác
`/queue/submit` ở 2 điểm: (1) khoá xác thực riêng (`public_submit_key`, không phải
`gas_api_key`) vì khoá này bị lộ ra trình duyệt công khai của mọi xã, không còn là bí mật
server-to-server; (2) tự kiểm tra lại xã/tuần/định dạng file thay vì tin trình duyệt, vì
Google Apps Script (vốn đã kiểm tra các điều kiện này trước khi chuyển tiếp) không còn đứng
giữa để chặn nữa. Xem CLAUDE.md mục "Web nộp báo cáo trực tiếp từ GitHub Pages"."""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import core
from webapp.config import get_settings
from webapp.services.http import client_ip
from webapp.services.rate_limit import queue_submit_limiter

router = APIRouter()

MAX_REQUEST_BYTES = 110 * 1024 * 1024
# Giới hạn riêng cho /queue/submit-xa: khớp đúng MAX_FILE_BYTES phía Code.gs (máy chủ phụ) để
# hai đường nộp có cùng ràng buộc — xã không thể "lách" giới hạn bằng cách đổi đường nộp.
MAX_PUBLIC_FILE_BYTES = 20 * 1024 * 1024
WEEK_PATTERN = re.compile(r"^\d{4}-W\d{2}$")
XLSX_SIGNATURE = b"PK\x03\x04"


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status)


def _constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


@router.post("/queue/submit")
async def submit(request: Request):
    settings = get_settings()

    content_length = request.headers.get("content-length", "")
    if content_length.isdigit() and int(content_length) > MAX_REQUEST_BYTES:
        return _error(413, "Yêu cầu vượt giới hạn 110 MB.")

    if not settings.config.gas_api_key:
        return _error(503, "Máy chủ chưa cấu hình khoá API cho Google Apps Script (gas_api_key).")
    provided_key = request.headers.get("x-gsbtn-password", "")
    if not _constant_time_equals(provided_key, settings.config.gas_api_key):
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


@router.post("/queue/submit-xa")
async def submit_xa(request: Request):
    settings = get_settings()

    content_length = request.headers.get("content-length", "")
    if content_length.isdigit() and int(content_length) > MAX_PUBLIC_FILE_BYTES:
        return _error(413, f"File vượt quá giới hạn {MAX_PUBLIC_FILE_BYTES // (1024 * 1024)} MB.")

    if not settings.config.public_submit_key:
        return _error(503, "Máy chủ chưa cấu hình khoá nộp trực tiếp (public_submit_key).")
    provided_key = request.headers.get("x-gsbtn-password", "")
    if not _constant_time_equals(provided_key, settings.config.public_submit_key):
        return _error(401, "Sai khoá nộp báo cáo.")

    body = await request.body()
    if len(body) > MAX_PUBLIC_FILE_BYTES:
        return _error(413, f"File vượt quá giới hạn {MAX_PUBLIC_FILE_BYTES // (1024 * 1024)} MB.")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _error(400, "Nội dung yêu cầu không phải JSON hợp lệ.")
    if not isinstance(payload, dict):
        return _error(400, "Nội dung yêu cầu không hợp lệ.")

    commune = core.strip_text(payload.get("commune", ""))
    week = core.strip_text(payload.get("week", ""))
    rate_key = f"{client_ip(request)}:{commune[:80]}"
    if not queue_submit_limiter.allow(rate_key):
        return _error(429, "Gửi quá nhiều lần trong thời gian ngắn, thử lại sau vài phút.")

    # Từ đây trở xuống là các kiểm tra mà trước nay Code.gs đã làm hộ trước khi chuyển tiếp —
    # bắt buộc phải làm lại ở đây vì trình duyệt gọi thẳng, không còn qua Apps Script nữa.
    if commune not in core.OFFICIAL_COMMUNES:
        return _error(400, "Đơn vị không hợp lệ — vui lòng chọn đúng tên từ danh sách gợi ý.")
    if not WEEK_PATTERN.match(week):
        return _error(400, "Định dạng tuần báo cáo không hợp lệ.")
    if week > core.current_iso_week():
        return _error(400, "Không được chọn tuần báo cáo trong tương lai.")

    content_b64 = payload.get("content_base64")
    if not isinstance(content_b64, str) or not content_b64:
        return _error(400, "Thiếu nội dung file Excel.")
    try:
        file_bytes = base64.b64decode(content_b64.encode("ascii"), validate=True)
    except (ValueError, binascii.Error):
        return _error(400, "Nội dung file không phải base64 hợp lệ.")
    if len(file_bytes) > MAX_PUBLIC_FILE_BYTES:
        return _error(413, f"File vượt quá giới hạn {MAX_PUBLIC_FILE_BYTES // (1024 * 1024)} MB.")
    if not file_bytes.startswith(XLSX_SIGNATURE):
        return _error(400, "Nội dung không đúng định dạng file Excel (.xlsx/.xlsm).")

    try:
        result = core.queue_submit(
            commune, week, str(payload.get("file_name", "du_lieu.xlsx")), file_bytes,
            source="server_chinh", submitted_by=str(payload.get("submitted_by", "")),
            db_path=settings.db_path,
        )
    except ValueError as exc:
        core.log_audit(
            "queue_submit_xa_rejected", actor="xa", commune=commune, detail=str(exc),
            ip=client_ip(request), db_path=settings.db_path,
        )
        return _error(400, str(exc))

    return JSONResponse({"ok": True, "result": result})
