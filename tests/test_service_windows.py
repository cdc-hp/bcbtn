"""Kiểm thử Giai đoạn 8: service_windows.py — xem TASKS.md.

Không cài đặt/gỡ dịch vụ Windows thật trong test (cần quyền Administrator, có tác dụng phụ trên
máy chạy test) — chỉ kiểm tra các hàm thuần (`query_status`/`restart_service`) hoạt động đúng
khi dịch vụ CHƯA được cài đặt (đúng trạng thái thật trên máy chạy CI/dev), và cấu trúc class
dịch vụ đúng quy ước pywin32 mà không đăng ký gì với Windows."""

from __future__ import annotations

import pytest

import service_windows


def test_query_status_when_not_installed():
    status = service_windows.query_status()
    assert status["installed"] is False
    assert status["running"] is False
    assert status["state"]


def test_restart_service_when_not_installed_or_no_permission():
    result = service_windows.restart_service()
    assert result["ok"] is False
    assert result["message"]


@pytest.mark.skipif(not hasattr(service_windows, "_build_service_class"), reason="service_windows chưa có _build_service_class")
def test_service_class_has_correct_win32_conventions():
    try:
        import win32serviceutil
    except ImportError:
        pytest.skip("pywin32 chưa cài đặt trên máy này")
    service_class = service_windows._build_service_class()
    assert issubclass(service_class, win32serviceutil.ServiceFramework)
    assert service_class._svc_name_ == service_windows.SERVICE_NAME
    assert service_class._svc_display_name_ == service_windows.SERVICE_DISPLAY_NAME
    assert hasattr(service_class, "SvcStop")
    assert hasattr(service_class, "SvcDoRun")


def test_resolve_cli_mode():
    # "host" = KHÔNG có tham số dòng lệnh — đúng cách Windows SCM tự gọi lại exe đã đăng ký để
    # thật sự chạy dịch vụ (không phải "install"/"start"/...). Lỗi thật đã gặp: trước đây nhánh
    # này lẫn chung với "manage" (gọi HandleCommandLine — chỉ in usage() rồi thoát ngay khi
    # không có tham số, khiến dịch vụ cài xong nhưng luôn về trạng thái Stopped).
    assert service_windows._resolve_cli_mode(["service_windows.py"]) == "host"
    assert service_windows._resolve_cli_mode(["service_windows.py", "install"]) == "manage"
    assert service_windows._resolve_cli_mode(["service_windows.py", "debug"]) == "manage"
    assert service_windows._resolve_cli_mode(["service_windows.py", "run"]) == "run"


def test_importing_module_has_no_side_effects():
    """Import module không được tự ý đặt GIAM_SAT_DICH_BENH_DATA_DIR — chỉ nhánh `service` của
    `__main__` mới làm việc đó, để `import service_windows` từ test khác không bị ảnh hưởng."""
    import importlib
    import os

    had_key_before = "GIAM_SAT_DICH_BENH_DATA_DIR" in os.environ
    value_before = os.environ.get("GIAM_SAT_DICH_BENH_DATA_DIR")
    importlib.reload(service_windows)
    if had_key_before:
        assert os.environ.get("GIAM_SAT_DICH_BENH_DATA_DIR") == value_before
    else:
        assert "GIAM_SAT_DICH_BENH_DATA_DIR" not in os.environ


def test_run_server_reads_host_port_from_config(monkeypatch, tmp_path):
    """run_server() phải đọc server_host/server_port từ deployment_config hiện tại rồi truyền
    đúng cho uvicorn.Config — không gọi server.run() thật (sẽ block vô hạn)."""
    import deployment_config

    monkeypatch.setattr(deployment_config, "CONFIG_PATH", tmp_path / "deployment.json")
    config = deployment_config.load_config()
    config.server_host = "127.0.0.1"
    config.server_port = 19999
    deployment_config.save_config(config)

    captured = {}

    class FakeServer:
        def __init__(self, config):
            captured["host"] = config.host
            captured["port"] = config.port
            self.should_exit = False

        def run(self):
            captured["ran"] = True

    import uvicorn
    monkeypatch.setattr(uvicorn, "Server", FakeServer)

    service_windows.run_server()
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 19999
    assert captured["ran"] is True
