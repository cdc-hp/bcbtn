"""Phân trang dùng chung cho các trang danh sách CHƯA phân trang (Hàng đợi, Tài khoản, Tài khoản
xã, Nhật ký kiểm toán, Lịch sử nhập, Sao lưu) — mẫu tối giản, cắt trang bằng Python SAU KHI đã có
đủ danh sách (mỗi router vẫn tự fetch tới ngưỡng hiện có của mình, vd `core.list_import_queue`
limit 2000, `core.list_audit_log` limit 200 — không cần thêm OFFSET ở SQL vì các ngưỡng đó đã đủ
dùng). `records_list.html`/`webapp/routers/records.py` (Ca bệnh/Ổ dịch) đã phân trang chuẩn ở tầng
SQL từ trước — module này KHÔNG thay thế mẫu đó, chỉ dùng cho các trang còn lại."""

from __future__ import annotations

from typing import Any

DEFAULT_PAGE_SIZE = 50


def paginate(rows: list[Any], page: int, page_size: int = DEFAULT_PAGE_SIZE) -> tuple[list[Any], dict[str, int]]:
    """Trả về `(rows_của_trang, info)` — `info` gồm `page` (đã kẹp về khoảng hợp lệ), `total`
    (tổng số dòng trước khi cắt trang), `total_pages`, `page_size`. Trang vượt quá tổng số trang
    tự kẹp về trang cuối (không lỗi, không trả rỗng gây hiểu nhầm "không có dữ liệu")."""
    page_size = max(1, int(page_size))
    total = len(rows)
    total_pages = max(1, -(-total // page_size))  # ceil division
    page = max(1, min(int(page) if page else 1, total_pages))
    start = (page - 1) * page_size
    return rows[start:start + page_size], {
        "page": page, "total": total, "total_pages": total_pages, "page_size": page_size,
    }
