"""Chạy Web App thủ công kèm biểu tượng khay hệ thống — thay cho trải nghiệm "mở app.py, để
chạy nền, thu vào khay hệ thống" của bản desktop cũ (đã gỡ bỏ, xem TASKS.md). Dùng khi máy CDC
CHƯA/KHÔNG muốn đăng ký `service_windows.py` làm dịch vụ Windows thật (vd. máy demo, máy phát
triển, hoặc giai đoạn dùng thử trước khi cài đặt dịch vụ chính thức) — cách chạy khuyến nghị lâu
dài vẫn là dịch vụ Windows (tự khởi động cùng máy, không cần ai đăng nhập desktop).

Chạy: `python service_tray.py` (hoặc bấm đúp `Chay_May_Chu.bat` cùng thư mục). Icon khay hệ
thống hiện ngay khi server đã sẵn sàng nhận request; chuột phải có "Mở trình duyệt" (tới trang
đăng nhập) và "Thoát" (dừng hẳn máy chủ, không chỉ ẩn cửa sổ — khác nút X thu vào khay của bản
desktop cũ).

QUAN TRỌNG (cùng lý do với `service_windows.py`): biến môi trường
`GIAM_SAT_DICH_BENH_DATA_DIR` phải được đặt TRƯỚC khi `deployment_config`/`core`/`webapp` được
import lần đầu (các module đó tính đường dẫn dữ liệu ngay lúc import). Vì vậy các import đó nằm
cục bộ trong hàm, không đặt ở đầu file — chỉ `win32api`/`win32con`/`win32gui`/`service_windows`
(module không đụng tới core.py/deployment_config.py) mới an toàn để import sớm.
"""

from __future__ import annotations

import ctypes
import os
import threading

import win32api
import win32con
import win32gui

import service_windows

WM_TRAYICON = win32con.WM_USER + 20
ID_TRAY_ICON = 1
ID_MENU_OPEN = 1001
ID_MENU_EXIT = 1002

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


class TrayApp:
    def __init__(self, config):
        self.config = config
        self.server = None
        self.hwnd = self._create_window()
        self._add_tray_icon()
        if self.config.prevent_sleep:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)

    def _create_window(self) -> int:
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = self._wnd_proc
        wc.lpszClassName = "CDCGiamSatDichBenhTray"
        wc.hInstance = win32api.GetModuleHandle(None)
        class_atom = win32gui.RegisterClass(wc)
        return win32gui.CreateWindow(
            class_atom, "CDC Giám sát dịch bệnh", 0, 0, 0, 0, 0, 0, 0, wc.hInstance, None,
        )

    def _add_tray_icon(self) -> None:
        icon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
        flags = win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP
        tooltip = f"CDC Giám sát dịch bệnh — cổng {self.config.server_port} (đang khởi động...)"
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, (self.hwnd, ID_TRAY_ICON, flags, WM_TRAYICON, icon, tooltip))

    def mark_ready(self) -> None:
        """Gọi sau khi Uvicorn đã thật sự mở cổng lắng nghe — đổi tooltip để CDC biết server sẵn
        sàng nhận request, không chỉ tiến trình đã khởi động."""
        icon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
        flags = win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP
        tooltip = f"CDC Giám sát dịch bệnh — đang chạy, cổng {self.config.server_port}"
        win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, (self.hwnd, ID_TRAY_ICON, flags, WM_TRAYICON, icon, tooltip))

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAYICON:
            if lparam == win32con.WM_LBUTTONDBLCLK:
                self._open_browser()
            elif lparam == win32con.WM_RBUTTONUP:
                self._show_menu()
            return 0
        if msg == win32con.WM_COMMAND:
            cmd = win32api.LOWORD(wparam)
            if cmd == ID_MENU_OPEN:
                self._open_browser()
            elif cmd == ID_MENU_EXIT:
                self._quit()
            return 0
        if msg == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _open_browser(self) -> None:
        import webbrowser

        port = self.config.server_port or 8765
        webbrowser.open(f"http://127.0.0.1:{port}/cdc/login")

    def _show_menu(self) -> None:
        menu = win32gui.CreatePopupMenu()
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_MENU_OPEN, "Mở trình duyệt")
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_MENU_EXIT, "Thoát (dừng máy chủ)")
        pos = win32gui.GetCursorPos()
        win32gui.SetForegroundWindow(self.hwnd)
        win32gui.TrackPopupMenu(menu, win32con.TPM_LEFTALIGN, pos[0], pos[1], 0, self.hwnd, None)
        win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)

    def _quit(self) -> None:
        if self.server is not None:
            self.server.should_exit = True
        if self.config.prevent_sleep:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self.hwnd, ID_TRAY_ICON))
        win32gui.DestroyWindow(self.hwnd)


def _run_server(app: TrayApp) -> None:
    import uvicorn

    uv_config = uvicorn.Config(
        "webapp.main:app", host=app.config.server_host or "0.0.0.0", port=int(app.config.server_port or 8765),
        log_level="info", log_config=None,
    )
    app.server = uvicorn.Server(uv_config)

    def _mark_ready_once_started():
        import time

        while app.server is not None and not app.server.started and not app.server.should_exit:
            time.sleep(0.2)
        if app.server is not None and app.server.started:
            app.mark_ready()

    threading.Thread(target=_mark_ready_once_started, daemon=True).start()
    app.server.run()


def main() -> None:
    os.environ.setdefault("GIAM_SAT_DICH_BENH_DATA_DIR", service_windows.DEFAULT_SERVICE_DATA_DIR)

    import deployment_config

    config = deployment_config.load_config()
    app = TrayApp(config)
    threading.Thread(target=_run_server, args=(app,), daemon=True).start()
    win32gui.PumpMessages()


if __name__ == "__main__":
    main()
