from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

MANIFEST_FILE_ID = "1gEk9LH7k40FgN7Ry68m0SHih-CwcF4l9"
DRIVE_DOWNLOAD_URL = "https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"
USER_AGENT = "GiamSatDichBenh-Updater/1.0"

GITHUB_REPO = "cdc-hp/bcbtn"
GITHUB_LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"
# Tên tệp cài đặt ứng với từng chế độ triển khai, khớp OutputBaseFilename trong setup*.iss
# và tên tệp release.yml đóng gói — xem CLAUDE.md mục "File chính".
GITHUB_ASSET_NAME_BY_MODE = {
    "standalone": "GiamSatDichBenh-Setup-v{version}.exe",
    "server": "GiamSatDichBenh-Server-Setup-v{version}.exe",
    "workstation": "GiamSatDichBenh-Admin-Setup-v{version}.exe",
}


class UpdateError(RuntimeError):
    """Lỗi có thể hiển thị trực tiếp cho người dùng."""


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    release_file_id: str
    file_name: str
    sha256: str
    notes: str = ""
    published_at: str = ""
    package_root: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UpdateInfo":
        required = ("version", "release_file_id", "file_name", "sha256")
        missing = [key for key in required if not str(data.get(key, "")).strip()]
        if missing:
            raise UpdateError("Tệp cập nhật thiếu trường: " + ", ".join(missing))
        sha256 = str(data["sha256"]).strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise UpdateError("Mã kiểm tra SHA-256 trong tệp cập nhật không hợp lệ.")
        return cls(
            version=str(data["version"]).strip(),
            release_file_id=str(data["release_file_id"]).strip(),
            file_name=str(data["file_name"]).strip(),
            sha256=sha256,
            notes=str(data.get("notes", "")).strip(),
            published_at=str(data.get("published_at", "")).strip(),
            package_root=str(data.get("package_root", "")).strip(),
        )


@dataclass(frozen=True)
class GithubReleaseInfo:
    version: str
    notes: str
    asset_name: str
    download_url: str
    sha256: str


def _parse_sha256sums(text: str, file_name: str) -> str:
    """Đọc tệp SHA256SUMS.txt (định dạng `<hash>  <tên tệp>`) và trả mã hash của đúng tệp."""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[1].strip().lstrip("*") == file_name:
            return parts[0].strip().lower()
    return ""


def fetch_github_release(mode: str, timeout: int = 15) -> GithubReleaseInfo:
    """Đọc bản phát hành mới nhất trên GitHub Releases ứng với chế độ triển khai hiện tại."""
    template = GITHUB_ASSET_NAME_BY_MODE.get(mode)
    if not template:
        raise UpdateError(f"Không có gói cài đặt GitHub cho chế độ triển khai '{mode}'.")
    request = urllib.request.Request(
        GITHUB_LATEST_RELEASE_API,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise UpdateError(f"GitHub từ chối yêu cầu kiểm tra bản phát hành (HTTP {exc.code}).") from exc
    except urllib.error.URLError as exc:
        raise UpdateError(f"Không kết nối được GitHub: {exc.reason}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("Không đọc được thông tin bản phát hành từ GitHub.") from exc
    if not isinstance(data, dict):
        raise UpdateError("Nội dung bản phát hành GitHub không hợp lệ.")
    version = str(data.get("tag_name", "")).strip().lstrip("vV")
    if not version:
        raise UpdateError("Bản phát hành trên GitHub thiếu số phiên bản.")
    assets = {str(a.get("name", "")): str(a.get("browser_download_url", "")) for a in data.get("assets", []) if isinstance(a, dict)}
    asset_name = template.format(version=version)
    download_url = assets.get(asset_name)
    if not download_url:
        raise UpdateError(f"Không tìm thấy tệp {asset_name} trong bản phát hành GitHub mới nhất ({GITHUB_RELEASES_PAGE}).")
    sha256 = ""
    sums_url = assets.get("SHA256SUMS.txt")
    if sums_url:
        try:
            sums_text = download_url_to_bytes(sums_url, timeout=timeout).decode("utf-8", errors="ignore")
            sha256 = _parse_sha256sums(sums_text, asset_name)
        except UpdateError:
            sha256 = ""
    return GithubReleaseInfo(
        version=version,
        notes=str(data.get("body", "") or "").strip(),
        asset_name=asset_name,
        download_url=download_url,
        sha256=sha256,
    )


def download_url_to_bytes(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise UpdateError(f"Tải tệp thất bại (HTTP {exc.code}): {url}") from exc
    except urllib.error.URLError as exc:
        raise UpdateError(f"Không kết nối được: {exc.reason}") from exc


def download_url_to_file(
    url: str,
    destination: Path,
    progress: Callable[[int, int | None], None] | None = None,
    timeout: int = 120,
) -> Path:
    """Tải tệp từ URL bất kỳ (vd. GitHub Releases) kèm báo tiến độ, khác download_drive_file ở
    chỗ không cần dò trang HTML lỗi của Drive vì GitHub trả thẳng nội dung nhị phân."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            total_header = response.headers.get("Content-Length")
            total = int(total_header) if total_header and total_header.isdigit() else None
            downloaded = 0
            with destination.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    if progress:
                        progress(downloaded, total)
        return destination
    except urllib.error.HTTPError as exc:
        raise UpdateError(f"Tải bản cập nhật thất bại (HTTP {exc.code}).") from exc
    except urllib.error.URLError as exc:
        raise UpdateError(f"Không kết nối được máy chủ tải bản cập nhật: {exc.reason}") from exc


def launch_installer_and_exit(installer_path: Path) -> None:
    """Mở trình cài đặt Inno Setup vừa tải. setup*.iss đã tự giữ nguyên deployment.json có sẵn
    (không hỏi lại cấu hình) khi phát hiện đây là lần chạy thứ hai trở đi, nên chỉ cần mở lên;
    CloseApplications=yes trong setup*.iss tự lo việc đóng ứng dụng đang chạy khi cần."""
    if os.name != "nt":
        raise UpdateError("Tự cập nhật hiện chỉ hỗ trợ Windows.")
    subprocess.Popen([str(Path(installer_path).resolve())], close_fds=True)


def version_key(version: str) -> tuple[int, ...]:
    """Chuyển 1.2.10-beta thành (1, 2, 10) để so sánh an toàn."""
    numbers = re.findall(r"\d+", version)
    return tuple(int(x) for x in numbers) or (0,)


def is_newer_version(remote_version: str, current_version: str) -> bool:
    remote = list(version_key(remote_version))
    current = list(version_key(current_version))
    length = max(len(remote), len(current))
    remote.extend([0] * (length - len(remote)))
    current.extend([0] * (length - len(current)))
    return tuple(remote) > tuple(current)


def drive_download_url(file_id: str) -> str:
    file_id = str(file_id).strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,}", file_id):
        raise UpdateError("ID tệp Google Drive không hợp lệ.")
    return DRIVE_DOWNLOAD_URL.format(file_id=file_id)


def _looks_like_html(data: bytes, content_type: str = "") -> bool:
    prefix = data[:512].lstrip().lower()
    return "text/html" in content_type.lower() or prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html")


def download_drive_file(
    file_id: str,
    destination: Path | None = None,
    progress: Callable[[int, int | None], None] | None = None,
    timeout: int = 60,
) -> bytes | Path:
    """Tải tệp Drive công khai. Khi destination=None trả bytes, ngược lại trả Path."""
    request = urllib.request.Request(drive_download_url(file_id), headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            total_header = response.headers.get("Content-Length")
            total = int(total_header) if total_header and total_header.isdigit() else None
            if destination is None:
                data = response.read()
                if _looks_like_html(data, content_type):
                    raise UpdateError(
                        "Google Drive trả về trang đăng nhập thay vì tệp cập nhật. "
                        "Hãy đặt quyền chia sẻ tệp thành ‘Bất kỳ ai có đường liên kết – Người xem’."
                    )
                return data

            destination = Path(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            downloaded = 0
            first_chunk = b""
            with destination.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    if not first_chunk:
                        first_chunk = chunk[:512]
                    output.write(chunk)
                    downloaded += len(chunk)
                    if progress:
                        progress(downloaded, total)
            if _looks_like_html(first_chunk, content_type):
                destination.unlink(missing_ok=True)
                raise UpdateError(
                    "Không tải được gói cập nhật vì tệp Google Drive chưa được chia sẻ công khai."
                )
            return destination
    except urllib.error.HTTPError as exc:
        raise UpdateError(f"Google Drive từ chối tải tệp (HTTP {exc.code}).") from exc
    except urllib.error.URLError as exc:
        raise UpdateError(f"Không kết nối được Google Drive: {exc.reason}") from exc


def fetch_manifest(file_id: str = MANIFEST_FILE_ID, timeout: int = 15) -> UpdateInfo:
    raw = download_drive_file(file_id, timeout=timeout)
    assert isinstance(raw, bytes)
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("Tệp update_manifest.json không phải JSON hợp lệ.") from exc
    if not isinstance(data, dict):
        raise UpdateError("Nội dung tệp cập nhật không hợp lệ.")
    return UpdateInfo.from_dict(data)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_download(path: Path, expected_sha256: str) -> None:
    actual = sha256_file(path)
    if actual.lower() != expected_sha256.lower():
        Path(path).unlink(missing_ok=True)
        raise UpdateError(
            "Gói cập nhật tải về không đúng mã SHA-256. Tệp đã bị xóa để bảo đảm an toàn."
        )


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def create_windows_apply_script(
    zip_path: Path,
    install_dir: Path,
    package_root: str,
    launch_path: Path,
    launch_argument: str = "",
) -> Path:
    """Tạo PowerShell chạy sau khi app đóng để thay tệp, giữ nguyên data/backups."""
    fd, script_name = tempfile.mkstemp(prefix="giam_sat_dich_benh_update_", suffix=".ps1")
    os.close(fd)
    script_path = Path(script_name)
    script = f"""
$ErrorActionPreference = 'Stop'
$ProcessId = {os.getpid()}
$ZipPath = {_ps_quote(str(Path(zip_path).resolve()))}
$InstallDir = {_ps_quote(str(Path(install_dir).resolve()))}
$PackageRoot = {_ps_quote(package_root)}
$LaunchPath = {_ps_quote(str(Path(launch_path).resolve()))}
$LaunchArgument = {_ps_quote(launch_argument)}
$LogPath = Join-Path $env:TEMP 'giam_sat_dich_benh_update.log'

try {{
    Wait-Process -Id $ProcessId -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 800
    $Staging = Join-Path $env:TEMP ('giam_sat_update_' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $Staging -Force | Out-Null
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $Staging -Force

    if ($PackageRoot -and (Test-Path (Join-Path $Staging $PackageRoot))) {{
        $Source = Join-Path $Staging $PackageRoot
    }} else {{
        $Children = @(Get-ChildItem -LiteralPath $Staging -Force)
        if ($Children.Count -eq 1 -and $Children[0].PSIsContainer) {{
            $Source = $Children[0].FullName
        }} else {{
            $Source = $Staging
        }}
    }}

    $Preserve = @('data', 'backups', 'update_cache', 'app_password.hash', 'update_config.json')
    Get-ChildItem -LiteralPath $Source -Force | ForEach-Object {{
        if ($Preserve -notcontains $_.Name) {{
            $Target = Join-Path $InstallDir $_.Name
            if (Test-Path $Target) {{ Remove-Item -LiteralPath $Target -Recurse -Force }}
            Copy-Item -LiteralPath $_.FullName -Destination $Target -Recurse -Force
        }}
    }}

    Remove-Item -LiteralPath $Staging -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
    'Update completed at ' + (Get-Date) | Set-Content -LiteralPath $LogPath -Encoding UTF8

    if ($LaunchArgument) {{
        Start-Process -FilePath $LaunchPath -ArgumentList @(( '\"' + $LaunchArgument + '\"')) -WorkingDirectory $InstallDir
    }} else {{
        Start-Process -FilePath $LaunchPath -WorkingDirectory $InstallDir
    }}
}} catch {{
    ($_ | Out-String) | Set-Content -LiteralPath $LogPath -Encoding UTF8
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show(
        'Cập nhật không hoàn tất. Xem nhật ký tại: ' + $LogPath,
        'Giám sát dịch bệnh', 'OK', 'Error'
    ) | Out-Null
}}
""".strip()
    script_path.write_text(script, encoding="utf-8-sig")
    return script_path


def launch_update_and_exit(zip_path: Path, install_dir: Path, package_root: str = "") -> None:
    if os.name != "nt":
        raise UpdateError("Tự cập nhật hiện chỉ hỗ trợ Windows.")
    if getattr(sys, "frozen", False):
        launch_path = Path(sys.executable)
        launch_argument = ""
    else:
        launch_path = Path(sys.executable)
        launch_argument = str((Path(install_dir) / "app.py").resolve())
    script = create_windows_apply_script(
        zip_path=zip_path,
        install_dir=install_dir,
        package_root=package_root,
        launch_path=launch_path,
        launch_argument=launch_argument,
    )
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        cwd=str(install_dir),
        close_fds=True,
        creationflags=creationflags,
    )
