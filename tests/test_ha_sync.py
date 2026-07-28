"""Kiểm thử `ha_sync.py` (đồng bộ máy chủ dự phòng — failover thủ công, xem CLAUDE.md mục "Máy
chủ dự phòng"). KHÔNG gọi mạng thật — luôn giả lập `urlopen`/`ha_sync.pull_snapshot_from_peer`,
theo đúng mẫu `tests/test_scheduler.py` (đồng bộ máy chủ phụ Google Apps Script)."""

from __future__ import annotations

from pathlib import Path

import pytest

import backup_manager
import core
import deployment_config
import ha_sync


@pytest.fixture(autouse=True)
def _reset_ha_state(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(core, "DATA_DIR", tmp_path / "data")
    core.DATA_DIR.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(core, "DB_PATH", core.DATA_DIR / "test.db")
    monkeypatch.setattr(deployment_config, "CONFIG_PATH", tmp_path / "deployment.json")
    monkeypatch.setattr(backup_manager, "CONFIG_PATH", tmp_path / "backup_policy.json")
    monkeypatch.setattr(backup_manager, "LOCAL_BACKUP_DIR", tmp_path / "backups")
    core.init_db(core.DB_PATH)

    ha_sync._state.update({
        "running": False, "last_run_at": "", "last_success_at": "", "last_result": None, "last_error": "",
    })
    yield
    if ha_sync._run_lock.locked():
        ha_sync._run_lock.release()


def _configure_standby(url: str = "http://192.168.1.20:8765", key: str = "khoa-may-toi-may", interval: int = 15) -> None:
    config = deployment_config.load_config()
    config.server_role = "standby"
    config.peer_server_url = url
    config.peer_shared_key = key
    config.standby_sync_interval_minutes = interval
    deployment_config.save_config(config)


def test_run_standby_pull_skips_when_primary():
    result = ha_sync.run_standby_pull_once(db_path=core.DB_PATH)
    assert result["skipped"] is True
    assert "không phải máy dự phòng" in result["reason"]


def test_run_standby_pull_skips_when_unconfigured():
    config = deployment_config.load_config()
    config.server_role = "standby"
    deployment_config.save_config(config)
    result = ha_sync.run_standby_pull_once(db_path=core.DB_PATH)
    assert result["skipped"] is True
    assert "Chưa cấu hình máy kia" in result["reason"]


def test_run_standby_pull_success(monkeypatch, tmp_path: Path):
    _configure_standby()
    fake_snapshot = tmp_path / "fake_snapshot.db"
    fake_snapshot.write_bytes(b"")
    core.init_db(fake_snapshot)  # snapshot hợp lệ để restore_backup không từ chối

    monkeypatch.setattr(ha_sync, "pull_snapshot_from_peer", lambda url, key, timeout=60: fake_snapshot)
    result = ha_sync.run_standby_pull_once(db_path=core.DB_PATH)
    assert "restored_from" in result

    status = ha_sync.get_status()
    assert status["last_error"] == ""
    assert status["last_success_at"]
    assert status["server_role"] == "standby"
    assert status["configured"] is True

    actions = core.list_audit_log(db_path=core.DB_PATH)
    assert any(a["action"] == "ha_standby_pull" for a in actions)


def test_run_standby_pull_error_logged(monkeypatch):
    _configure_standby()

    def _boom(url, key, timeout=60):
        raise ConnectionError("máy kia không phản hồi")

    monkeypatch.setattr(ha_sync, "pull_snapshot_from_peer", _boom)
    result = ha_sync.run_standby_pull_once(db_path=core.DB_PATH)
    assert "error" in result
    status = ha_sync.get_status()
    assert "không phản hồi" in status["last_error"]

    actions = core.list_audit_log(db_path=core.DB_PATH)
    assert any(a["action"] == "ha_standby_pull_error" for a in actions)


def test_pull_snapshot_from_peer_rejects_corrupt_file(monkeypatch, tmp_path: Path):
    class _FakeResponse:
        def read(self):
            return b"khong-phai-file-sqlite-hop-le"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(ha_sync, "urlopen", lambda request, timeout=60: _FakeResponse())
    with pytest.raises(ValueError, match="toàn vẹn"):
        ha_sync.pull_snapshot_from_peer("http://192.168.1.20:8765", "khoa")


def test_notify_peer_demote_returns_false_on_network_error(monkeypatch):
    from urllib.error import URLError

    def _boom(request, timeout=8):
        raise URLError("khong ket noi duoc")

    monkeypatch.setattr(ha_sync, "urlopen", _boom)
    assert ha_sync.notify_peer_demote("http://192.168.1.20:8765", "khoa") is False


def test_notify_peer_demote_returns_false_when_no_peer_url():
    assert ha_sync.notify_peer_demote("", "khoa") is False


def test_check_peer_role_returns_none_on_network_error(monkeypatch):
    from urllib.error import URLError

    def _boom(request, timeout=5):
        raise URLError("khong ket noi duoc")

    monkeypatch.setattr(ha_sync, "urlopen", _boom)
    assert ha_sync.check_peer_role("http://192.168.1.20:8765", "khoa") is None


def test_resolve_startup_conflict_skips_when_not_primary():
    config = deployment_config.load_config()
    config.server_role = "standby"
    deployment_config.save_config(config)
    result = ha_sync.resolve_startup_conflict(db_path=core.DB_PATH)
    assert result["skipped"] is True


def test_resolve_startup_conflict_skips_when_peer_unconfigured():
    result = ha_sync.resolve_startup_conflict(db_path=core.DB_PATH)
    assert result["skipped"] is True
    assert deployment_config.load_config().server_role == "primary"


def test_resolve_startup_conflict_skips_when_peer_not_primary(monkeypatch):
    config = deployment_config.load_config()
    config.peer_server_url = "http://192.168.1.20:8765"
    config.peer_shared_key = "khoa"
    deployment_config.save_config(config)
    monkeypatch.setattr(ha_sync, "check_peer_role", lambda url, key: "standby")
    result = ha_sync.resolve_startup_conflict(db_path=core.DB_PATH)
    assert result["skipped"] is True
    assert deployment_config.load_config().server_role == "primary"


def test_resolve_startup_conflict_self_demotes_when_peer_also_primary(monkeypatch):
    config = deployment_config.load_config()
    config.peer_server_url = "http://192.168.1.20:8765"
    config.peer_shared_key = "khoa"
    deployment_config.save_config(config)
    monkeypatch.setattr(ha_sync, "check_peer_role", lambda url, key: "primary")
    catch_up_calls: list[bool] = []
    monkeypatch.setattr(
        ha_sync, "run_standby_pull_once",
        lambda db_path=None: catch_up_calls.append(True) or {"restored_from": "fake.db"},
    )
    result = ha_sync.resolve_startup_conflict(db_path=core.DB_PATH)
    assert result["demoted"] is True
    assert result["catch_up"] == {"restored_from": "fake.db"}
    assert deployment_config.load_config().server_role == "standby"
    assert catch_up_calls == [True]  # kéo bù ngay lúc tự hạ cấp, không đợi chu kỳ định kỳ tiếp theo

    actions = core.list_audit_log(db_path=core.DB_PATH)
    assert any(a["action"] == "ha_startup_self_demoted" for a in actions)
