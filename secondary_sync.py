"""Đồng bộ dữ liệu từ máy chủ phụ (Google Apps Script + Sheet + Drive) vào hàng đợi chính.

Khi máy chủ chính offline, Trạm Y tế xã nộp file qua Web App của Google Apps Script
(``google_apps_script/MayChuPhu.gs``) — script đó lưu file vào Google Drive và ghi một dòng
"chờ đồng bộ" vào Google Sheet đóng vai trò hàng đợi tạm. Module này chạy trên máy chủ chính:
khi máy chủ chính online trở lại, nó gọi Web App để lấy các dòng đang chờ, tải file, đẩy vào
``import_queue`` cục bộ (``core.queue_submit`` với ``source="server_phu"``), rồi báo lại cho
Apps Script đánh dấu đã đồng bộ để không kéo trùng lần sau.

Chỉ dùng thư viện chuẩn (``urllib``) — không thêm phụ thuộc mới.
"""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import core

DEFAULT_TIMEOUT = 30


def _call(webapp_url: str, params: dict[str, str] | None = None, body: dict[str, Any] | None = None, timeout: int = DEFAULT_TIMEOUT) -> Any:
    if not webapp_url:
        raise ValueError("Chưa cấu hình địa chỉ máy chủ phụ (secondary_webapp_url).")
    url = webapp_url.rstrip("/")
    if params:
        query = "&".join(f"{key}={value}" for key, value in params.items())
        url = f"{url}?{query}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST" if data else "GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise ConnectionError(f"Máy chủ phụ trả lỗi HTTP {exc.code}.") from exc
    except URLError as exc:
        raise ConnectionError(f"Không kết nối được máy chủ phụ: {exc.reason}") from exc
    if not payload.get("ok"):
        raise RuntimeError(payload.get("error") or "Máy chủ phụ trả về lỗi không xác định.")
    return payload.get("result")


def list_pending_secondary(webapp_url: str, shared_key: str, timeout: int = DEFAULT_TIMEOUT) -> list[dict[str, Any]]:
    """Lấy danh sách các lần nộp đang chờ đồng bộ trên máy chủ phụ."""
    result = _call(webapp_url, params={"action": "list_pending", "key": shared_key}, timeout=timeout)
    return result or []


def mark_synced(webapp_url: str, shared_key: str, rows: list[int], timeout: int = DEFAULT_TIMEOUT) -> None:
    """Báo cho máy chủ phụ biết các dòng đã được kéo về, tránh đồng bộ lại lần sau."""
    if not rows:
        return
    _call(webapp_url, body={"action": "mark_synced", "key": shared_key, "rows": rows}, timeout=timeout)


def pull_secondary_queue(
    webapp_url: str,
    shared_key: str,
    *,
    db_path: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Kéo toàn bộ dữ liệu đang chờ trên máy chủ phụ vào hàng đợi nhập liệu cục bộ.

    Trả về số lượng đã kéo thành công và lỗi từng dòng (nếu có); không dừng giữa chừng khi một
    dòng lỗi — tiếp tục các dòng còn lại rồi báo cáo tổng hợp.
    """
    db_path = db_path or core.DB_PATH
    pending = list_pending_secondary(webapp_url, shared_key, timeout=timeout)
    pulled: list[int] = []
    errors: list[dict[str, Any]] = []
    for item in pending:
        row = item.get("row")
        try:
            content = item.get("content_base64") or ""
            if not content:
                raise ValueError("Thiếu nội dung file trên máy chủ phụ.")
            file_bytes = base64.b64decode(content.encode("ascii"), validate=True)
            core.queue_submit(
                str(item.get("commune", "")),
                str(item.get("week", "")),
                str(item.get("file_name", "du_lieu.xlsx")),
                file_bytes,
                source="server_phu",
                submitted_by=str(item.get("submitted_by", "")),
                db_path=db_path,
            )
            pulled.append(int(row))
        except Exception as exc:
            errors.append({"row": row, "error": str(exc)})
    if pulled:
        mark_synced(webapp_url, shared_key, pulled, timeout=timeout)
    return {"pending_count": len(pending), "pulled_count": len(pulled), "errors": errors}
