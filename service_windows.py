"""Windows Service wrapper cho Web App tập trung — Giai đoạn 8 (xem TASKS.md), thay mô hình cũ
"mở app.py, để chạy nền, thu vào khay hệ thống": Web App giờ chạy như 1 dịch vụ Windows
(`CDCGiamSatDichBenh`), tự khởi động cùng máy, không cần ai đăng nhập desktop.

Dùng dòng lệnh (cần quyền Administrator để cài/gỡ/bật/tắt dịch vụ — bản thân file này không tự
xin quyền nâng cao):
    python service_windows.py install   # đăng ký dịch vụ (chạy 1 lần, thường do bộ cài gọi)
    python service_windows.py start     # bật
    python service_windows.py stop      # tắt
    python service_windows.py remove    # gỡ đăng ký
    python service_windows.py debug     # chạy trực tiếp trong console để xem log, Ctrl+C để dừng
    python service_windows.py run       # giống debug nhưng KHÔNG qua khung dịch vụ (win32
                                         # serviceutil) — dùng khi phát triển/kiểm thử nhanh,
                                         # không cần đăng ký gì với Windows.

`run_server()` là phần lõi thật sự chạy Uvicorn — dùng chung cho cả `SvcDoRun` (khi chạy như
dịch vụ) lẫn lệnh `run` (khi chạy tay) để đảm bảo 2 đường chạy giống hệt nhau, không lệch hành vi
giữa "chạy thử" và "chạy thật"."""

from __future__ import annotations

import sys
from typing import Any

import deployment_config

SERVICE_NAME = "CDCGiamSatDichBenh"
SERVICE_DISPLAY_NAME = "CDC Hải Phòng - Giám sát dịch bệnh"
SERVICE_DESCRIPTION = (
    "Web App tập trung quản lý ca bệnh/ổ dịch CDC Hải Phòng (FastAPI/Uvicorn). "
    "Quản trị qua trình duyệt tại /cdc/login."
)


def run_server(service: Any = None) -> None:
    """Khởi chạy Uvicorn phục vụ `webapp.main:app` theo cấu hình hiện tại (server_host/
    server_port trong deployment_config.py); trả về khi `server.should_exit` được đặt (do
    `service.SvcStop()` gọi, hoặc Ctrl+C ở chế độ chạy tay)."""
    import uvicorn

    config = deployment_config.load_config()
    uv_config = uvicorn.Config(
        "webapp.main:app", host=config.server_host or "0.0.0.0", port=int(config.server_port or 8765),
        log_level="info",
    )
    server = uvicorn.Server(uv_config)
    if service is not None:
        service.server = server
    server.run()


def query_status() -> dict[str, Any]:
    """Tra trạng thái dịch vụ đã cài trên Windows — không cần quyền Administrator (chỉ đọc).
    Dùng cho `/cdc/cau-hinh` hiển thị "dịch vụ đang chạy/đã dừng/chưa cài đặt"."""
    try:
        import win32service
        import win32serviceutil
    except ImportError:
        return {"installed": False, "running": False, "state": "Chưa cài pywin32 (chỉ có trên Windows)."}
    try:
        status_code = win32serviceutil.QueryServiceStatus(SERVICE_NAME)[1]
    except Exception:
        return {"installed": False, "running": False, "state": "Chưa cài đặt dịch vụ Windows."}
    labels = {
        win32service.SERVICE_STOPPED: "Đã dừng", win32service.SERVICE_START_PENDING: "Đang khởi động",
        win32service.SERVICE_STOP_PENDING: "Đang dừng", win32service.SERVICE_RUNNING: "Đang chạy",
        win32service.SERVICE_CONTINUE_PENDING: "Đang tiếp tục", win32service.SERVICE_PAUSE_PENDING: "Đang tạm dừng",
        win32service.SERVICE_PAUSED: "Đã tạm dừng",
    }
    return {
        "installed": True, "running": status_code == win32service.SERVICE_RUNNING,
        "state": labels.get(status_code, str(status_code)),
    }


def restart_service() -> dict[str, Any]:
    """Khởi động lại dịch vụ — cần quyền Administrator (tiến trình Web App khi chạy dưới dạng
    dịch vụ Windows thường có đủ quyền tự quản chính mình). Không tự xin nâng quyền; nếu tiến
    trình gọi hàm này thiếu quyền hoặc dịch vụ chưa được cài (vd. đang chạy `uvicorn --reload`
    lúc phát triển), trả lỗi rõ ràng thay vì crash."""
    try:
        import win32serviceutil
    except ImportError:
        return {"ok": False, "message": "Chưa cài pywin32 — không thể điều khiển dịch vụ Windows."}
    try:
        win32serviceutil.RestartService(SERVICE_NAME)
        return {"ok": True, "message": "Đã gửi yêu cầu khởi động lại dịch vụ."}
    except Exception as exc:
        return {
            "ok": False,
            "message": (
                "Không thể khởi động lại dịch vụ (có thể chưa cài đặt dịch vụ Windows, đang chạy "
                f"ở chế độ phát triển, hoặc thiếu quyền Administrator): {exc}"
            ),
        }


def _build_service_class():
    """Chỉ định nghĩa class dịch vụ khi import pywin32 thành công — cho phép `query_status()`/
    `restart_service()` vẫn hoạt động trên máy không có pywin32 (vd. macOS/Linux dùng cho phát
    triển) mà không lỗi ngay từ lúc import module này."""
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil

    class CDCWebAppService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY_NAME
        _svc_description_ = SERVICE_DESCRIPTION

        def __init__(self, args):
            super().__init__(args)
            self.stop_event = win32event.CreateEvent(None, 0, 0, None)
            self.server = None

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            if self.server is not None:
                self.server.should_exit = True
            win32event.SetEvent(self.stop_event)

        def SvcDoRun(self):
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE, servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, ""),
            )
            run_server(self)

    return CDCWebAppService


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        run_server()
    else:
        ServiceClass = _build_service_class()
        import win32serviceutil

        win32serviceutil.HandleCommandLine(ServiceClass)
