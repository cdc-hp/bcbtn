"""Kiểm thử Giai đoạn 7: webapp/scheduler.py (đồng bộ máy chủ phụ chạy nền qua APScheduler) —
xem TASKS.md. Không gọi mạng thật — luôn giả lập secondary_sync.pull_secondary_queue."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

import core
import deployment_config
import secondary_sync
from webapp import scheduler


@pytest.fixture(autouse=True)
def _reset_scheduler_state(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(core, "DATA_DIR", tmp_path / "data")
    core.DATA_DIR.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(core, "DB_PATH", core.DATA_DIR / "test.db")
    monkeypatch.setattr(deployment_config, "CONFIG_PATH", tmp_path / "deployment.json")
    core.init_db(core.DB_PATH)

    scheduler._state.update({
        "running": False, "last_run_at": "", "last_success_at": "", "last_result": None, "last_error": "",
    })
    yield
    scheduler.shutdown()
    if scheduler._run_lock.locked():
        scheduler._run_lock.release()


def _configure_secondary(url: str = "https://example.com/exec", key: str = "khoa_bi_mat", interval: int = 20) -> None:
    config = deployment_config.load_config()
    config.secondary_webapp_url = url
    config.secondary_shared_key = key
    config.secondary_sync_interval_minutes = interval
    deployment_config.save_config(config)


def test_run_sync_once_skips_when_unconfigured():
    result = scheduler.run_sync_once(db_path=core.DB_PATH)
    assert result["skipped"] is True
    status = scheduler.get_status()
    assert status["configured"] is False


def test_run_sync_once_success(monkeypatch):
    _configure_secondary()
    monkeypatch.setattr(
        secondary_sync, "pull_secondary_queue",
        lambda url, key, db_path=None, timeout=30: {"pending_count": 2, "pulled_count": 2, "errors": []},
    )
    result = scheduler.run_sync_once(db_path=core.DB_PATH)
    assert result == {"pending_count": 2, "pulled_count": 2, "errors": []}
    status = scheduler.get_status()
    assert status["configured"] is True
    assert status["last_error"] == ""
    assert status["last_success_at"]
    assert status["last_result"]["pulled_count"] == 2

    actions = core.list_audit_log(db_path=core.DB_PATH)
    assert any(a["action"] == "secondary_sync_pull" for a in actions)


def test_run_sync_once_error_logged(monkeypatch):
    _configure_secondary()

    def _boom(url, key, db_path=None, timeout=30):
        raise ConnectionError("máy chủ phụ không phản hồi")

    monkeypatch.setattr(secondary_sync, "pull_secondary_queue", _boom)
    result = scheduler.run_sync_once(db_path=core.DB_PATH)
    assert "error" in result
    status = scheduler.get_status()
    assert "không phản hồi" in status["last_error"]

    actions = core.list_audit_log(db_path=core.DB_PATH)
    assert any(a["action"] == "secondary_sync_error" for a in actions)


def test_run_sync_once_does_not_overlap(monkeypatch):
    _configure_secondary()
    started = threading.Event()
    release = threading.Event()

    def _slow(url, key, db_path=None, timeout=30):
        started.set()
        release.wait(timeout=5)
        return {"pending_count": 0, "pulled_count": 0, "errors": []}

    monkeypatch.setattr(secondary_sync, "pull_secondary_queue", _slow)
    thread = threading.Thread(target=scheduler.run_sync_once, kwargs={"db_path": core.DB_PATH})
    thread.start()
    assert started.wait(timeout=5)

    concurrent_result = scheduler.run_sync_once(db_path=core.DB_PATH)
    assert concurrent_result.get("skipped") is True

    release.set()
    thread.join(timeout=5)


def test_start_registers_job_with_configured_interval():
    _configure_secondary(interval=45)
    scheduler.start()
    status = scheduler.get_status()
    assert status["scheduler_running"] is True
    assert status["interval_minutes"] == 45
    assert status["next_run_at"]


def test_start_is_idempotent():
    _configure_secondary()
    scheduler.start()
    first = scheduler._scheduler
    scheduler.start()
    assert scheduler._scheduler is first


def test_shutdown_resets_state():
    _configure_secondary()
    scheduler.start()
    scheduler.shutdown()
    status = scheduler.get_status()
    assert status["scheduler_running"] is False
    assert status["next_run_at"] == ""
