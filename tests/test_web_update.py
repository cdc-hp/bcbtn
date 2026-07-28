from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import core
import update_manager
from webapp.services import web_update


def test_update_job_backs_up_downloads_verifies_and_launches(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(core, "UPDATE_CACHE_DIR", tmp_path / "update_cache")
    monkeypatch.setattr(web_update, "_job_running", True)
    events = []
    payload = b"signed-installer-content"
    backup = tmp_path / "backups" / "gsbtn_before_update.db"
    backup.parent.mkdir()
    backup.write_bytes(b"database-backup")

    def fake_backup(db_path, *, kind):
        events.append(("backup", str(db_path), kind))
        return backup

    def fake_download(url, destination, progress, timeout):
        events.append(("download", url, timeout))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        progress(len(payload), len(payload))
        return destination

    def fake_launch(path, version):
        events.append(("launch", path.name, version))

    monkeypatch.setattr(web_update.backup_manager, "create_backup", fake_backup)
    monkeypatch.setattr(web_update.update_manager, "download_url_to_file", fake_download)
    monkeypatch.setattr(web_update, "launch_silent_installer", fake_launch)
    monkeypatch.setattr(web_update.core, "log_audit", lambda *args, **kwargs: events.append(("audit", args[0])))

    info = update_manager.GithubReleaseInfo(
        version="9.9.9",
        notes="",
        asset_name="CDC-GiamSatDichBenh-Server-Setup-v9.9.9.exe",
        download_url="https://example.test/update.exe",
        sha256=hashlib.sha256(payload).hexdigest(),
    )
    web_update.perform_queued_update(info, actor="super", db_path=tmp_path / "data" / "test.db")

    assert [event[0] for event in events] == ["backup", "download", "audit", "launch"]
    status = web_update.get_public_status()
    assert status["status"] == "installing"
    assert status["progress_percent"] == 96
    assert status["backup_name"] == backup.name
    assert web_update._job_running is False


def test_checksum_failure_deletes_installer_and_never_launches(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(core, "UPDATE_CACHE_DIR", tmp_path / "update_cache")
    monkeypatch.setattr(web_update, "_job_running", True)
    launched = []
    backup = tmp_path / "backup.db"
    backup.write_bytes(b"backup")
    monkeypatch.setattr(web_update.backup_manager, "create_backup", lambda *args, **kwargs: backup)

    def fake_download(_url, destination, progress, timeout):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"tampered")
        progress(8, 8)
        return destination

    monkeypatch.setattr(web_update.update_manager, "download_url_to_file", fake_download)
    monkeypatch.setattr(web_update, "launch_silent_installer", lambda *args: launched.append(args))
    monkeypatch.setattr(web_update.core, "log_audit", lambda *args, **kwargs: None)
    info = update_manager.GithubReleaseInfo(
        version="9.9.9", notes="", asset_name="CDC-GiamSatDichBenh-Server-Setup-v9.9.9.exe",
        download_url="https://example.test/update.exe", sha256="0" * 64,
    )

    web_update.perform_queued_update(info, actor="super", db_path=tmp_path / "test.db")

    assert not launched
    assert not (tmp_path / "update_cache" / info.asset_name).exists()
    assert web_update.get_public_status()["status"] == "failed"


def test_stuck_downloading_recovers_when_job_not_running(tmp_path: Path, monkeypatch):
    """Cạm bẫy đã gặp thật: dịch vụ khởi động lại/mất điện giữa chừng để lại trạng thái
    "downloading" vĩnh viễn trong file, dù không còn tiến trình nào thực sự đang chạy — phải tự
    phát hiện qua _job_running (chỉ True khi ĐANG chạy trong CHÍNH tiến trình hiện tại)."""
    monkeypatch.setattr(core, "UPDATE_CACHE_DIR", tmp_path / "update_cache")
    monkeypatch.setattr(web_update, "_job_running", False)
    web_update._write_status(status="downloading", message="Đang tải...", progress_percent=40, target_version="9.9.9")

    status = web_update.get_public_status()
    assert status["status"] == "failed"
    assert status["active"] is False
    assert "gián đoạn" in status["message"]


def test_actively_downloading_is_not_treated_as_stale(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(core, "UPDATE_CACHE_DIR", tmp_path / "update_cache")
    monkeypatch.setattr(web_update, "_job_running", True)
    web_update._write_status(status="downloading", message="Đang tải...", progress_percent=40, target_version="9.9.9")

    status = web_update.get_public_status()
    assert status["status"] == "downloading"
    assert status["active"] is True


def _write_status_with_timestamp(**changes) -> None:
    """Ghi thẳng file trạng thái, bỏ qua `web_update._write_status` (hàm đó luôn tự đặt lại
    `updated_at` bằng giờ hiện tại) — dùng để giả lập trạng thái đã cũ trong test."""
    path = web_update._status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {**web_update._default_status(), **changes}
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def test_stuck_installing_recovers_after_timeout(tmp_path: Path, monkeypatch):
    """Cạm bẫy đã gặp thật: bug Move-Item trên Windows PowerShell 5.1 (Move-Item -Force vẫn báo
    'Cannot create a file when that file already exists' dù đã có -Force khi file đích đã tồn
    tại) làm script cài đặt crash trước khi kịp ghi 'installed'/'failed', kẹt mãi ở 'installing'
    dù bộ cài thật đã chạy xong bên dưới (xem CLAUDE.md). Test này kiểm tra lối thoát dự phòng
    theo thời gian khi service chưa kịp khởi động lại với version mới để tự phát hiện qua
    so sánh version."""
    monkeypatch.setattr(core, "UPDATE_CACHE_DIR", tmp_path / "update_cache")
    monkeypatch.setattr(web_update, "_job_running", False)
    old_time = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat(timespec="seconds")
    _write_status_with_timestamp(
        status="installing", message="Đang cài...", progress_percent=96,
        target_version="9.9.9", updated_at=old_time,
    )

    status = web_update.get_public_status()
    assert status["status"] == "failed"
    assert "kiểm tra dịch vụ" in status["message"].lower() or "không hoàn tất" in status["message"].lower()


def test_recent_installing_is_not_treated_as_stale(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(core, "UPDATE_CACHE_DIR", tmp_path / "update_cache")
    monkeypatch.setattr(web_update, "_job_running", False)
    web_update._write_status(status="installing", message="Đang cài...", progress_percent=96, target_version="9.9.9")

    status = web_update.get_public_status()
    assert status["status"] == "installing"
    assert status["active"] is True


def test_reset_stuck_status_returns_to_idle_and_logs_audit(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(core, "UPDATE_CACHE_DIR", tmp_path / "update_cache")
    monkeypatch.setattr(core, "DATA_DIR", tmp_path / "data")
    core.DATA_DIR.mkdir(parents=True, exist_ok=True)
    db_path = core.DATA_DIR / "test.db"
    core.init_db(db_path)
    web_update._write_status(status="installing", message="Đang cài...", progress_percent=96, target_version="9.9.9")

    web_update.reset_stuck_status(actor="sa_admin", db_path=db_path)

    status = web_update.get_public_status()
    assert status["status"] == "idle"
    assert status["active"] is False
    actions = core.list_audit_log(db_path=db_path)
    assert any(a["action"] == "web_update_status_reset" for a in actions)
