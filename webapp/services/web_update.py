"""Cập nhật Web App tập trung từ GitHub Releases.

Luồng này chỉ được gọi bởi route đã khóa cho ``super_admin``. Trạng thái được ghi vào
``core.UPDATE_CACHE_DIR`` để trình duyệt vẫn đọc được sau khi bộ cài dừng và khởi động lại dịch vụ.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import backup_manager
import core
import update_manager

WEBAPP_RELEASE_MODE = "webapp_server"
STATUS_FILE_NAME = "web_update_status.json"
ACTIVE_STATES = frozenset({"queued", "backing_up", "downloading", "verifying", "installing"})

_state_lock = threading.RLock()
_job_lock = threading.Lock()
_job_running = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _status_path() -> Path:
    return Path(core.UPDATE_CACHE_DIR) / STATUS_FILE_NAME


def _default_status() -> dict[str, Any]:
    return {
        "status": "idle",
        "message": "Bấm kiểm tra để tìm bản phát hành mới nhất.",
        "current_version": core.VERSION,
        "target_version": "",
        "asset_name": "",
        "sha256": "",
        "notes": "",
        "progress_percent": None,
        "updated_at": _now(),
    }


def _read_status_unlocked() -> dict[str, Any]:
    path = _status_path()
    if not path.exists():
        return _default_status()
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return _default_status()
    if not isinstance(raw, dict):
        return _default_status()
    return {**_default_status(), **raw}


def _write_status(**changes: Any) -> dict[str, Any]:
    with _state_lock:
        state = _read_status_unlocked()
        state.update(changes)
        state["current_version"] = core.VERSION
        state["updated_at"] = _now()
        path = _status_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
        return state


# Các trạng thái này CHỈ tồn tại trong lúc perform_queued_update() còn đang chạy trong CHÍNH tiến
# trình hiện tại (_job_running=True suốt thời gian đó) — nếu thấy 1 trong các trạng thái này mà
# _job_running=False, chắc chắn tiến trình đã bị gián đoạn (dịch vụ khởi động lại/crash/mất điện
# giữa chừng), KHÔNG phải đang chạy bình thường. Không áp dụng cho "installing": trạng thái đó
# ghi xong là hàm return ngay (bộ cài chạy tiếp trong tiến trình PowerShell tách rời), nên
# _job_running tự về False rất nhanh kể cả khi mọi việc đang diễn ra bình thường.
_STALE_WHEN_JOB_NOT_RUNNING = frozenset({"queued", "backing_up", "downloading", "verifying"})
# "installing" không có tín hiệu tin cậy nào khác ngoài thời gian — bộ cài + khởi động lại dịch
# vụ bình thường mất tối đa vài phút; quá lâu hơn nhiều so với mức đó coi là kẹt.
_INSTALLING_STALE_AFTER_SECONDS = 15 * 60


def _seconds_since(iso_timestamp: str) -> float:
    if not iso_timestamp:
        return float("inf")
    try:
        stamp = datetime.fromisoformat(iso_timestamp)
    except ValueError:
        return float("inf")
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - stamp).total_seconds()


def get_public_status() -> dict[str, Any]:
    """Trả trạng thái không chứa URL tải nội bộ; tự nhận ra cập nhật đã xong sau khi service chạy
    lại, VÀ tự nhận ra trạng thái "đang chạy" bị kẹt (tiến trình cập nhật đã chết nhưng chưa kịp
    ghi lại lỗi — vd dịch vụ khởi động lại/mất điện giữa chừng) để không khoá chết nút "Kiểm tra
    cập nhật" mãi mãi (xem CLAUDE.md — cạm bẫy đã gặp thật: kẹt ở "installing" do bug Move-Item)."""
    with _state_lock:
        state = _read_status_unlocked()
        target = str(state.get("target_version", ""))
        status = state.get("status")
        if (
            target
            and status in ACTIVE_STATES | {"installed"}
            and not update_manager.is_newer_version(target, core.VERSION)
        ):
            state = _write_status(
                status="complete",
                message=f"Đã cập nhật thành công lên phiên bản {core.VERSION}.",
                progress_percent=100,
            )
        elif status in _STALE_WHEN_JOB_NOT_RUNNING and not _job_running:
            state = _write_status(
                status="failed",
                message=(
                    "Lần cập nhật trước bị gián đoạn giữa chừng (có thể do dịch vụ khởi động lại "
                    "hoặc mất điện) — bấm \"Kiểm tra cập nhật\" để thử lại."
                ),
                progress_percent=0,
            )
        elif status == "installing" and _seconds_since(str(state.get("updated_at", ""))) > _INSTALLING_STALE_AFTER_SECONDS:
            state = _write_status(
                status="failed",
                message=(
                    "Bước cài đặt không hoàn tất trong thời gian dự kiến — kiểm tra dịch vụ Windows "
                    "thủ công, hoặc bấm \"Kiểm tra cập nhật\" để thử lại."
                ),
                progress_percent=0,
            )
        state["current_version"] = core.VERSION
        state["active"] = state.get("status") in ACTIVE_STATES
        state["release_url"] = update_manager.GITHUB_RELEASES_PAGE
        return state


def reset_stuck_status(*, actor: str, db_path: str | Path) -> dict[str, Any]:
    """Đặt lại trạng thái về "idle" theo yêu cầu thủ công của super-admin — lối thoát dự phòng khi
    admin thấy giao diện kẹt nhưng cơ chế tự phát hiện ở get_public_status() vì lý do nào đó chưa
    xử lý được (vd trạng thái "installing" chưa đủ 15 phút). An toàn kể cả khi có 1 job THẬT đang
    chạy trong tiến trình này: reset chỉ xoá bản ghi trạng thái hiển thị, không huỷ job đang chạy
    (job vẫn tự ghi đè lại trạng thái mới nhất ở lần cập nhật tiến độ kế tiếp của chính nó)."""
    state = _write_status(
        status="idle", message="Đã đặt lại trạng thái cập nhật.", progress_percent=None,
        target_version="", asset_name="", sha256="", notes="",
    )
    core.log_audit("web_update_status_reset", actor=actor, db_path=db_path)
    return state


def check_for_update() -> tuple[update_manager.GithubReleaseInfo, dict[str, Any]]:
    current = get_public_status()
    if current.get("active"):
        raise update_manager.UpdateError("Một tiến trình cập nhật đang chạy. Hãy chờ tiến trình hoàn tất.")
    try:
        info = update_manager.fetch_github_release(WEBAPP_RELEASE_MODE)
    except update_manager.UpdateError as exc:
        _write_status(status="check_failed", message=str(exc), progress_percent=None)
        raise

    common = {
        "target_version": info.version,
        "asset_name": info.asset_name,
        "sha256": info.sha256,
        "notes": info.notes[:8000],
        "progress_percent": None,
    }
    if not update_manager.is_newer_version(info.version, core.VERSION):
        state = _write_status(
            **common,
            status="current",
            message=f"Hệ thống đang dùng phiên bản mới nhất ({core.VERSION}).",
        )
    elif not info.sha256:
        state = _write_status(
            **common,
            status="blocked",
            message="Có bản mới nhưng thiếu mã SHA-256; hệ thống từ chối tự cập nhật để bảo đảm an toàn.",
        )
    else:
        state = _write_status(
            **common,
            status="available",
            message=f"Đã tìm thấy phiên bản {info.version}, sẵn sàng cập nhật.",
        )
    return info, state


def auto_install_supported(service_status: dict[str, Any]) -> bool:
    return os.name == "nt" and bool(service_status.get("installed")) and bool(service_status.get("running"))


def queue_update() -> update_manager.GithubReleaseInfo:
    global _job_running
    with _job_lock:
        if _job_running or get_public_status().get("active"):
            raise update_manager.UpdateError("Một tiến trình cập nhật đang chạy. Không thể tạo yêu cầu thứ hai.")
        info, state = check_for_update()
        if state["status"] == "current":
            raise update_manager.UpdateError(f"Phiên bản {core.VERSION} đã là phiên bản mới nhất.")
        if state["status"] != "available" or not info.sha256:
            raise update_manager.UpdateError(str(state["message"]))
        expected_name = f"CDC-GiamSatDichBenh-Server-Setup-v{info.version}.exe"
        if info.asset_name != expected_name or Path(info.asset_name).name != info.asset_name:
            raise update_manager.UpdateError("Tên gói cập nhật Web Server không hợp lệ.")
        _job_running = True
        _write_status(
            status="queued",
            message=f"Đã xếp lịch cập nhật lên {info.version}.",
            progress_percent=0,
        )
        return info


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _create_installer_helper(installer_path: Path, target_version: str) -> Path:
    """Tạo tiến trình độc lập vì bộ cài phải dừng chính service đang phục vụ request hiện tại."""
    cache_dir = Path(core.UPDATE_CACHE_DIR).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    script_path = cache_dir / "apply_web_update.ps1"
    status_path = _status_path().resolve()
    log_path = (cache_dir / f"installer-v{target_version}.log").resolve()
    script = f"""
$ErrorActionPreference = 'Stop'
$Installer = {_ps_quote(str(installer_path.resolve()))}
$StatusPath = {_ps_quote(str(status_path))}
$LogPath = {_ps_quote(str(log_path))}
$TargetVersion = {_ps_quote(target_version)}

function Write-UpdateStatus([string]$State, [string]$Message, [int]$Progress) {{
  # $StatusPath LUÔN đã tồn tại (Python đã ghi "installing" trước khi script này chạy) —
  # Move-Item -Force có bug đã biết trên Windows PowerShell 5.1: vẫn báo "Cannot create a file
  # when that file already exists" dù đã có -Force (tái hiện được 100%, không phải do tranh chấp
  # khoá file). Dùng thẳng [System.IO.File]::Copy(..., $true) để ghi đè tin cậy, không qua
  # Move-Item — lỗi này từng khiến CẢ 2 nhánh (thành công lẫn catch) đều crash trước khi kịp ghi
  # trạng thái cuối, làm giao diện kẹt mãi ở "installing" dù bộ cài đã chạy xong bên dưới.
  try {{
    $Payload = @{{
      status = $State
      message = $Message
      target_version = $TargetVersion
      progress_percent = $Progress
      updated_at = (Get-Date).ToUniversalTime().ToString('o')
    }} | ConvertTo-Json
    $TempPath = $StatusPath + '.tmp'
    Set-Content -LiteralPath $TempPath -Value $Payload -Encoding UTF8
    [System.IO.File]::Copy($TempPath, $StatusPath, $true)
    Remove-Item -LiteralPath $TempPath -Force -ErrorAction SilentlyContinue
  }} catch {{
    # Không để lỗi ghi trạng thái (vd đĩa đầy, bị khoá) làm mất luôn kết quả cài đặt thật —
    # ghi thêm vào log để còn biết đường tra, nhưng không throw tiếp.
    ($_ | Out-String) | Add-Content -LiteralPath $LogPath -Encoding UTF8 -ErrorAction SilentlyContinue
  }}
}}

Start-Sleep -Seconds 2
try {{
  $Arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', ('/LOG=' + $LogPath))
  $Process = Start-Process -FilePath $Installer -ArgumentList $Arguments -Wait -PassThru -WindowStyle Hidden
  if ($Process.ExitCode -ne 0) {{ throw ('Bộ cài kết thúc với mã ' + $Process.ExitCode) }}
  Write-UpdateStatus 'installed' ('Bộ cài phiên bản ' + $TargetVersion + ' đã hoàn tất; đang chờ Web App xác nhận.') 100
}} catch {{
  Write-UpdateStatus 'failed' ('Cập nhật không hoàn tất: ' + $_.Exception.Message + '. Xem nhật ký: ' + $LogPath) 0
}}
""".strip()
    script_path.write_text(script, encoding="utf-8-sig")
    return script_path


def launch_silent_installer(installer_path: Path, target_version: str) -> None:
    if os.name != "nt":
        raise update_manager.UpdateError("Tự cập nhật Web App chỉ hỗ trợ máy chủ Windows đã cài dịch vụ.")
    helper = _create_installer_helper(installer_path, target_version)
    creationflags = (
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    subprocess.Popen(
        [
            "powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
            "-ExecutionPolicy", "Bypass", "-File", str(helper),
        ],
        cwd=str(Path(core.UPDATE_CACHE_DIR).resolve()),
        close_fds=True,
        creationflags=creationflags,
    )


def perform_queued_update(
    info: update_manager.GithubReleaseInfo,
    *,
    actor: str,
    db_path: str | Path,
) -> None:
    """Tác vụ nền: sao lưu, tải, xác minh rồi giao bộ cài cho helper độc lập."""
    global _job_running
    try:
        _write_status(status="backing_up", message="Đang sao lưu và kiểm tra toàn vẹn CSDL...", progress_percent=2)
        backup_path = backup_manager.create_backup(db_path, kind="before_update")

        cache_dir = Path(core.UPDATE_CACHE_DIR).resolve()
        cache_dir.mkdir(parents=True, exist_ok=True)
        installer_path = cache_dir / info.asset_name

        last_percent = -1

        def on_progress(downloaded: int, total: int | None) -> None:
            nonlocal last_percent
            percent = min(88, max(5, int(downloaded * 83 / total) + 5)) if total else None
            if percent is None or percent >= last_percent + 2:
                last_percent = percent if percent is not None else last_percent
                _write_status(
                    status="downloading",
                    message=f"Đang tải {info.asset_name}...",
                    progress_percent=percent,
                    downloaded_bytes=downloaded,
                    total_bytes=total,
                    backup_name=backup_path.name,
                )

        update_manager.download_url_to_file(info.download_url, installer_path, on_progress, timeout=300)
        _write_status(
            status="verifying",
            message="Đang xác minh mã SHA-256 của bộ cài...",
            progress_percent=92,
            backup_name=backup_path.name,
        )
        update_manager.verify_download(installer_path, info.sha256)
        core.log_audit(
            "web_update_installer_verified",
            actor=actor,
            detail=f"version={info.version}; asset={info.asset_name}; backup={backup_path.name}",
            db_path=db_path,
        )
        _write_status(
            status="installing",
            message="Đã xác minh an toàn. Dịch vụ sẽ tạm ngắt để cài đặt và tự khởi động lại.",
            progress_percent=96,
            backup_name=backup_path.name,
        )
        launch_silent_installer(installer_path, info.version)
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        _write_status(status="failed", message=f"Cập nhật không hoàn tất: {message}", progress_percent=0)
        try:
            core.log_audit("web_update_failed", actor=actor, detail=message, db_path=db_path)
        except Exception:
            pass
    finally:
        with _job_lock:
            _job_running = False
