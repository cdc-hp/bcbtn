"""Tạo file xuất tạm thời để trả về qua `FileResponse` rồi tự xoá sau khi gửi xong — dùng chung
cho `/cdc/xuat-du-lieu` và `/cdc/loc-trung` (xuất kết quả quét). Không ghi vào `QUEUE_DIR`/thư
mục dữ liệu chính vì đây là file tạm, không thuộc dữ liệu nghiệp vụ cần giữ lại."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from starlette.background import BackgroundTask
from starlette.responses import FileResponse


def make_temp_export_path(suffix: str) -> Path:
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="cdc_export_")
    os.close(fd)
    return Path(path)


def file_download_response(path: Path, download_name: str) -> FileResponse:
    return FileResponse(
        path, filename=download_name, background=BackgroundTask(lambda: path.unlink(missing_ok=True)),
    )
