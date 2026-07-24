"""Kiểm thử đường dẫn templates/static của webapp/ là tuyệt đối, không phụ thuộc thư mục làm
việc hiện tại — hồi quy cho lỗi thật gặp phải khi chạy như dịch vụ Windows: Windows SCM khởi
động tiến trình với thư mục làm việc mặc định là System32, khiến chuỗi tương đối
"webapp/templates" không trỏ tới đâu cả, StaticFiles báo lỗi ngay lúc import và dịch vụ crash
(xem TASKS.md, phần "Bổ sung sau khi phát hành v0.11.0")."""

from __future__ import annotations

from pathlib import Path

import webapp


def test_paths_are_absolute():
    assert Path(webapp.TEMPLATES_DIR).is_absolute()
    assert Path(webapp.STATIC_DIR).is_absolute()


def test_paths_point_to_real_directories():
    assert Path(webapp.TEMPLATES_DIR).is_dir()
    assert Path(webapp.STATIC_DIR).is_dir()
    assert (Path(webapp.TEMPLATES_DIR) / "base.html").exists()
    assert (Path(webapp.STATIC_DIR) / "vendor" / "bootstrap.min.css").exists()


def test_app_importable_from_unrelated_working_directory(tmp_path, monkeypatch):
    """Mô phỏng đúng tình huống Windows SCM: (re)load webapp.main trong khi thư mục làm việc
    KHÔNG liên quan gì tới mã nguồn — trước khi sửa, StaticFiles(directory="webapp/static") sẽ
    ném RuntimeError ngay tại đây (monkeypatch.chdir tự khôi phục cwd khi test kết thúc)."""
    import importlib

    import webapp.main as webapp_main

    monkeypatch.chdir(tmp_path)
    importlib.reload(webapp_main)
