"""Đồng bộ máy chủ phụ chạy nền qua APScheduler — Giai đoạn 7 (xem TASKS.md), thay
`MainWindow.run_auto_secondary_sync` kiểu `QTimer` của máy trạm PyQt6 cũ: chạy trong tiến trình
Uvicorn, không phụ thuộc có ai mở trình duyệt hay không.

`run_sync_once()` được canh giữ bởi `_run_lock` (không chặn) để đảm bảo không có 2 lần đồng bộ
chạy chồng lấp dù nguồn gọi là tác vụ định kỳ hay nút "Đồng bộ ngay" trên dashboard — nếu đang có
lần chạy khác, bỏ qua ngay (idempotent) thay vì xếp hàng chờ. Trạng thái đọc/ghi qua `_state_lock`
riêng (không dùng chung `_run_lock`) để việc xem trạng thái trên dashboard không bị treo trong
lúc một lần đồng bộ (có thể mất tới ``DEFAULT_TIMEOUT`` giây mỗi dòng) đang chạy."""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

import core
import deployment_config
import secondary_sync

_JOB_ID = "secondary_sync"

_run_lock = threading.Lock()
_state_lock = threading.Lock()
_state: dict[str, Any] = {
    "running": False, "last_run_at": "", "last_success_at": "", "last_result": None, "last_error": "",
}
_scheduler: BackgroundScheduler | None = None


def _set_state(**kwargs: Any) -> None:
    with _state_lock:
        _state.update(kwargs)


def get_status() -> dict[str, Any]:
    with _state_lock:
        status = dict(_state)
    config = deployment_config.load_config()
    status["configured"] = bool(config.secondary_webapp_url and config.secondary_shared_key)
    status["interval_minutes"] = config.secondary_sync_interval_minutes
    job = _scheduler.get_job(_JOB_ID) if _scheduler is not None else None
    status["next_run_at"] = (
        job.next_run_time.isoformat(sep=" ", timespec="seconds") if job and job.next_run_time else ""
    )
    status["scheduler_running"] = bool(_scheduler is not None and _scheduler.running)
    return status


def run_sync_once(db_path: str | None = None) -> dict[str, Any]:
    """Chạy 1 lần đồng bộ máy chủ phụ; bỏ qua im lặng nếu chưa cấu hình hoặc đang có lần chạy
    khác. Dùng chung cho cả tác vụ định kỳ lẫn nút "Đồng bộ ngay"."""
    if not _run_lock.acquire(blocking=False):
        return {"skipped": True, "reason": "Đang có lần đồng bộ khác đang chạy."}
    resolved_db_path = db_path or core.DB_PATH
    try:
        _set_state(running=True)
        config = deployment_config.load_config()
        if not (config.secondary_webapp_url and config.secondary_shared_key):
            return {"skipped": True, "reason": "Chưa cấu hình máy chủ phụ (secondary_webapp_url/secondary_shared_key)."}
        now = datetime.now().isoformat(sep=" ", timespec="seconds")
        try:
            result = secondary_sync.pull_secondary_queue(
                config.secondary_webapp_url, config.secondary_shared_key, db_path=resolved_db_path,
            )
            _set_state(last_run_at=now, last_success_at=now, last_result=result, last_error="")
            if result.get("pulled_count"):
                core.log_audit(
                    "secondary_sync_pull", actor="he_thong",
                    detail=f"pulled={result['pulled_count']}/{result['pending_count']}",
                    db_path=resolved_db_path,
                )
            return result
        except Exception as exc:
            _set_state(last_run_at=now, last_error=str(exc))
            core.log_audit("secondary_sync_error", actor="he_thong", detail=str(exc), db_path=resolved_db_path)
            return {"error": str(exc)}
    finally:
        _set_state(running=False)
        _run_lock.release()


def start(db_path: str | None = None) -> None:
    """Khởi động tác vụ nền — gọi 1 lần lúc Uvicorn startup (`webapp/main.py`). Đọc lại chu kỳ
    từ cấu hình mỗi lần gọi `run_sync_once` bên trong job, không cố định lúc khởi động, nên đổi
    `secondary_sync_interval_minutes` không cần khởi động lại tiến trình để có hiệu lực với NỘI
    DUNG đồng bộ — chỉ riêng CHU KỲ (`interval minutes` truyền cho APScheduler) cần khởi động lại
    mới đổi được, vì APScheduler không hỗ trợ đổi interval của job đang chạy mà không reschedule."""
    global _scheduler
    if _scheduler is not None:
        return
    config = deployment_config.load_config()
    interval = max(5, min(180, int(config.secondary_sync_interval_minutes or 20)))
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        run_sync_once, "interval", minutes=interval, id=_JOB_ID,
        max_instances=1, coalesce=True, kwargs={"db_path": db_path},
    )
    _scheduler.start()


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
