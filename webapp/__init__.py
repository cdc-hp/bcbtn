"""Web App tập trung (FastAPI/Uvicorn) — xem CLAUDE.md mục "Web App tập trung"."""

from __future__ import annotations

from pathlib import Path

# Đường dẫn TUYỆT ĐỐI tới webapp/templates và webapp/static, suy ra từ vị trí thật của package
# này (__file__) — KHÔNG dùng chuỗi tương đối "webapp/templates" như trước (lỗi thật gặp phải:
# khi chạy như dịch vụ Windows, Windows SCM khởi động tiến trình với thư mục làm việc mặc định
# là System32, không phải thư mục cài đặt, nên "webapp/templates" tương đối không trỏ tới đâu cả
# — StaticFiles kiểm tra thư mục tồn tại ngay lúc import nên toàn bộ webapp.main crash ngay khi
# khởi động, dịch vụ vào trạng thái Stopped ngay sau khi "Running" thoáng qua). Cách tính này
# đúng cả khi chạy từ mã nguồn lẫn khi đóng gói bằng PyInstaller (`__file__` của package vẫn trỏ
# đúng vào thư mục `_internal/webapp/` bên trong bản build).
PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = str(PACKAGE_DIR / "templates")
STATIC_DIR = str(PACKAGE_DIR / "static")
