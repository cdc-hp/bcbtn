from __future__ import annotations

import hashlib
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
