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
    python service_windows.py           # KHÔNG gõ tay — đây là cách chính Windows SCM tự gọi
                                         # lại exe đã đăng ký để thật sự chạy dịch vụ (xem
                                         # `_resolve_cli_mode`, nhánh "host").

`run_server()` là phần lõi thật sự chạy Uvicorn — dùng chung cho cả `SvcDoRun` (khi chạy như
dịch vụ) lẫn lệnh `run` (khi chạy tay) để đảm bảo 2 đường chạy giống hệt nhau, không lệch hành vi
giữa "chạy thử" và "chạy thật".

Khi chạy như dịch vụ thật (mọi lệnh trừ `run`), mặc định dùng
``C:\\ProgramData\\CDC Hai Phong\\GiamSatDichBenh`` làm thư mục dữ liệu (đúng yêu cầu triển khai
máy chủ tập trung) thay vì `%LOCALAPPDATA%` của app desktop cũ — ProgramData không gắn với 1 tài
khoản Windows cụ thể, phù hợp với tiến trình dịch vụ chạy dưới tài khoản hệ thống. Phải đặt biến
môi trường TRƯỚC khi `deployment_config`/`core`/... được import lần đầu (các module đó tính
đường dẫn ngay lúc import, không phải lười) — vì vậy `deployment_config` KHÔNG import ở đầu file
này mà import cục bộ trong `run_server()`, sau khi `__main__` đã kịp đặt biến môi trường."""

from __future__ import annotations

import os
import sys
from typing import Any

SERVICE_NAME = "CDCGiamSatDichBenh"
SERVICE_DISPLAY_NAME = "CDC Hải Phòng - Giám sát dịch bệnh"
SERVICE_DESCRIPTION = (
    "Web App tập trung quản lý ca bệnh/ổ dịch CDC Hải Phòng (FastAPI/Uvicorn). "
    "Quản trị qua trình duyệt tại /cdc/login."
)
DEFAULT_SERVICE_DATA_DIR = r"C:\ProgramData\CDC Hai Phong\GiamSatDichBenh"


def run_server(service: Any = None) -> None:
    """Khởi chạy Uvicorn phục vụ `webapp.main:app` theo cấu hình hiện tại (server_host/
    server_port trong deployment_config.py); trả về khi `server.should_exit` được đặt (do
    `service.SvcStop()` gọi, hoặc Ctrl+C ở chế độ chạy tay).

    Khi chạy dưới dạng dịch vụ Windows thật (`service` khác None), tiến trình KHÔNG có console
    (SCM không cấp console cho tiến trình dịch vụ) — `uvicorn.Config.__init__` mặc định tự gọi
    `configure_logging()` dựng formatter tô màu console ngay trong constructor, ném
    `ValueError: Unable to configure formatter 'default'` khi không có console thật (lỗi thật
    gặp phải, xem TASKS.md) và làm cả `SvcDoRun()` thất bại NGAY TRƯỚC KHI kịp mở cổng lắng
    nghe. `log_config=None` tắt hẳn bước này khi làm dịch vụ — không mất gì vì dù sao cũng không
    có console nào để hiện log tô màu; chế độ `run` (chạy tay, có console thật) vẫn giữ log đẹp
    như cũ."""
    import uvicorn

    import deployment_config

    config = deployment_config.load_config()
    uv_config = uvicorn.Config(
        "webapp.main:app", host=config.server_host or "0.0.0.0", port=int(config.server_port or 8765),
        log_level="info", log_config=None if service is not None else uvicorn.config.LOGGING_CONFIG,
    )
    server = uvicorn.Server(uv_config)
    if service is not None:
        service.server = server
    server.run()


def _service_status(service_name: str) -> dict[str, Any]:
    """Tra trạng thái 1 dịch vụ Windows BẤT KỲ theo tên — không cần quyền Administrator (chỉ
    đọc). Dùng chung cho dịch vụ chính (`SERVICE_NAME`) lẫn dịch vụ Cloudflared (tunnel công khai,
    xem `query_public_tunnel_status`)."""
    try:
        import win32service
        import win32serviceutil
    except ImportError:
        return {"installed": False, "running": False, "state": "Chưa cài pywin32 (chỉ có trên Windows)."}
    try:
        status_code = win32serviceutil.QueryServiceStatus(service_name)[1]
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


def query_status() -> dict[str, Any]:
    """Tra trạng thái dịch vụ đã cài trên Windows — không cần quyền Administrator (chỉ đọc).
    Dùng cho `/cdc/cau-hinh` hiển thị "dịch vụ đang chạy/đã dừng/chưa cài đặt"."""
    return _service_status(SERVICE_NAME)


# Tên dịch vụ Windows dùng chung cho tunnel công khai (cdc-hp.io.vn, Cloudflare Tunnel Replica) —
# KHÁC "CloudflaredHA" (tunnel riêng máy-tới-máy /noi-bo/ha/*, luôn phải chạy bất kể vai trò, xem
# CLAUDE.md mục "Máy chủ dự phòng"). Đặt cứng vì hướng dẫn cài đặt luôn dùng đúng tên này
# (`cloudflared.exe service install` mặc định đăng ký dịch vụ tên "Cloudflared").
PUBLIC_TUNNEL_SERVICE_NAME = "Cloudflared"


def query_public_tunnel_status() -> dict[str, Any]:
    """Tra trạng thái dịch vụ Cloudflared (tunnel công khai dùng chung) — chỉ đọc, an toàn gọi
    luôn bất kể `manage_public_tunnel_service` có bật hay không. Dùng cho `/cdc/cau-hinh` để CDC
    nhìn thấy ngay máy này có đang thật sự nối tunnel công khai hay không."""
    return _service_status(PUBLIC_TUNNEL_SERVICE_NAME)


def set_public_tunnel_running(should_run: bool) -> dict[str, Any]:
    """Bật/tắt dịch vụ Cloudflared (tunnel công khai dùng chung `cdc-hp.io.vn`) — dùng để máy dự
    phòng tự ngắt khỏi Cloudflare Tunnel Replica (Replica cân bằng tải giữa MỌI máy đang kết nối,
    không ưu tiên máy chính — sự cố thật đã gặp: máy dự phòng lỡ nhận request đọc công khai chứa
    dữ liệu cũ), tự nối lại khi được thăng làm máy chính. KHÔNG đụng tới dịch vụ "CloudflaredHA".
    Không bao giờ ném lỗi ra ngoài — đây là hành động phụ khi đổi vai trò, lỗi ở đây không được
    làm hỏng luồng thăng/hạ cấp chính; trả `{"ok": False, "message": ...}` nếu thiếu pywin32,
    chưa cài dịch vụ này, hoặc thiếu quyền Administrator."""
    try:
        import win32service
        import win32serviceutil
    except ImportError:
        return {"ok": False, "message": "Chưa cài pywin32 — không thể điều khiển dịch vụ Cloudflared."}
    try:
        status_code = win32serviceutil.QueryServiceStatus(PUBLIC_TUNNEL_SERVICE_NAME)[1]
    except Exception:
        return {"ok": False, "message": f"Chưa cài đặt dịch vụ '{PUBLIC_TUNNEL_SERVICE_NAME}' trên máy này."}
    is_running = status_code in (win32service.SERVICE_RUNNING, win32service.SERVICE_START_PENDING)
    if should_run == is_running:
        return {"ok": True, "message": "Đã đúng trạng thái, không cần đổi."}
    try:
        if should_run:
            win32serviceutil.StartService(PUBLIC_TUNNEL_SERVICE_NAME)
            return {"ok": True, "message": "Đã bật dịch vụ Cloudflared (nối lại tunnel công khai)."}
        win32serviceutil.StopService(PUBLIC_TUNNEL_SERVICE_NAME)
        return {"ok": True, "message": "Đã tắt dịch vụ Cloudflared (ngắt khỏi tunnel công khai)."}
    except Exception as exc:
        return {"ok": False, "message": f"Không thể đổi trạng thái dịch vụ Cloudflared: {exc}"}


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
            # servicemanager.LogMsg ghi vào Windows Event Log qua RegisterEventSource/
            # ReportEvent — đòi hỏi nguồn sự kiện (event source) đã được đăng ký sẵn trong
            # registry, trỏ tới 1 DLL thông báo (message DLL) biết định dạng các mã như
            # PYS_SERVICE_STARTED. Việc đăng ký này bình thường do pythonservice.exe (dịch vụ
            # Python KHÔNG đóng gói) lo, nhưng dịch vụ này tự host chính nó (không qua
            # pythonservice.exe, xem `_resolve_cli_mode`) nên không có đăng ký đó — gọi thẳng
            # LogMsg ném `pywintypes.error: RegisterEventSource/ReportEvent: Access is denied`
            # và làm SvcRun() thất bại ngay từ dòng đầu (lỗi thật gặp phải, xem TASKS.md). Việc
            # ghi Event Log chỉ mang tính thông tin, không cần thiết cho việc phục vụ HTTP — bỏ
            # qua an toàn nếu ghi lỗi thay vì để cả dịch vụ crash vì one dòng log.
            try:
                servicemanager.LogMsg(
                    servicemanager.EVENTLOG_INFORMATION_TYPE, servicemanager.PYS_SERVICE_STARTED,
                    (self._svc_name_, ""),
                )
            except Exception:
                pass
            run_server(self)

    return CDCWebAppService


def _resolve_cli_mode(argv: list[str]) -> str:
    """"run" = chạy tay để phát triển/kiểm thử (giữ nguyên GIAM_SAT_DICH_BENH_DATA_DIR hiện có,
    hoặc mặc định LOCALAPPDATA như trước). "manage" = lệnh gõ tay quản lý dịch vụ (install/
    start/stop/remove/debug) — đi qua `win32serviceutil.HandleCommandLine`. "host" = KHÔNG có
    tham số dòng lệnh nào — đây chính xác là cách Windows Service Control Manager (SCM) thật sự
    khởi động tiến trình của 1 dịch vụ đã đăng ký (SCM gọi thẳng exe đã đăng ký, không truyền
    "install"/"start"/gì cả).

    LỖI THẬT đã gặp (xem TASKS.md): trước đây nhánh "host" gọi nhầm
    `win32serviceutil.HandleCommandLine(ServiceClass)` — nhưng hàm đó khi nhận `len(argv) <= 1`
    chỉ in usage() rồi thoát ngay, KHÔNG tự suy ra "đang được SCM khởi động" như tưởng nhầm.
    Hệ quả: SCM khởi động tiến trình xong, tiến trình in usage rồi thoát ngay lập tức không làm
    gì — dịch vụ báo cài đặt/khởi động "thành công" (SCM không thấy lỗi) nhưng chỉ giây sau lại
    về trạng thái Stopped. Cách đúng để 1 exe tự host chính nó làm dịch vụ (không qua
    `pythonservice.exe`) là gọi thẳng `servicemanager.PrepareToHostSingle()` +
    `StartServiceCtrlDispatcher()` — xem nhánh "host" bên dưới."""
    if len(argv) > 1 and argv[1] == "run":
        return "run"
    if len(argv) <= 1:
        return "host"
    return "manage"


if __name__ == "__main__":
    _mode = _resolve_cli_mode(sys.argv)
    if _mode == "run":
        run_server()
    else:
        os.environ.setdefault("GIAM_SAT_DICH_BENH_DATA_DIR", DEFAULT_SERVICE_DATA_DIR)
        ServiceClass = _build_service_class()
        if _mode == "host":
            import servicemanager

            servicemanager.Initialize()
            servicemanager.PrepareToHostSingle(ServiceClass)
            servicemanager.StartServiceCtrlDispatcher()
        else:
            import win32serviceutil

            win32serviceutil.HandleCommandLine(ServiceClass)
