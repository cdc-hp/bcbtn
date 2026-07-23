import json
from pathlib import Path

import pytest

import update_manager as um


class _FakeResponse:
    def __init__(self, body: bytes, headers: dict | None = None):
        self._body = body
        self._consumed = False
        self.headers = headers or {}

    def read(self, *_args):
        # Mô phỏng hành vi stream thật: trả toàn bộ nội dung ở lần đọc đầu, rỗng (EOF) sau đó —
        # download_url_to_file() đọc theo vòng lặp cho tới khi gặp chunk rỗng mới dừng.
        if self._consumed:
            return b""
        self._consumed = True
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def test_version_compare():
    assert um.is_newer_version("0.2.0", "0.1.11")
    assert um.is_newer_version("1.0", "0.9.9")
    assert not um.is_newer_version("1.0.0", "1.0")
    assert not um.is_newer_version("0.1.1", "0.2.0")


def test_update_info_validation():
    info = um.UpdateInfo.from_dict({
        "version": "0.2.0",
        "release_file_id": "1d4hzkQvesNw16vFxSsvQX8ue-I1jt4MY",
        "file_name": "release.zip",
        "sha256": "a" * 64,
    })
    assert info.version == "0.2.0"
    with pytest.raises(um.UpdateError):
        um.UpdateInfo.from_dict({"version": "0.2.0"})


def test_drive_url_validation():
    url = um.drive_download_url("1d4hzkQvesNw16vFxSsvQX8ue-I1jt4MY")
    assert "drive.usercontent.google.com" in url
    with pytest.raises(um.UpdateError):
        um.drive_download_url("bad id")


def test_sha256_file(tmp_path: Path):
    target = tmp_path / "x.bin"
    target.write_bytes(b"abc")
    assert um.sha256_file(target) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_powershell_script_preserves_data(tmp_path: Path):
    zip_path = tmp_path / "release.zip"
    zip_path.write_bytes(b"zip")
    install_dir = tmp_path / "app"
    install_dir.mkdir()
    script = um.create_windows_apply_script(zip_path, install_dir, "root", Path("C:/Python/python.exe"), "app.py")
    text = script.read_text(encoding="utf-8-sig")
    assert "'data'" in text
    assert "'backups'" in text
    assert "Wait-Process" in text
    script.unlink()


def test_parse_sha256sums():
    text = (
        "60dd8d0c4501db7d7abda783ae5f368101da3e96b43d1ec32f1cbcfb30ecc01  GiamSatDichBenh-Setup-v0.8.0.exe\n"
        "95c1447daad501713d0a4926629bf265a01a9716b6819d6d1b5a6f186da7d30  GiamSatDichBenh-Server-Setup-v0.8.0.exe\n"
    )
    assert um._parse_sha256sums(text, "GiamSatDichBenh-Server-Setup-v0.8.0.exe") == "95c1447daad501713d0a4926629bf265a01a9716b6819d6d1b5a6f186da7d30"
    assert um._parse_sha256sums(text, "missing.exe") == ""


def test_fetch_github_release_picks_asset_for_mode(monkeypatch):
    release_body = json.dumps({
        "tag_name": "v0.8.0",
        "body": "Ghi chú phát hành",
        "assets": [
            {"name": "GiamSatDichBenh-Setup-v0.8.0.exe", "browser_download_url": "https://example.test/Setup.exe"},
            {"name": "GiamSatDichBenh-Server-Setup-v0.8.0.exe", "browser_download_url": "https://example.test/Server-Setup.exe"},
            {"name": "SHA256SUMS.txt", "browser_download_url": "https://example.test/SHA256SUMS.txt"},
        ],
    }).encode("utf-8")
    sums_body = b"deadbeef" * 8 + b"  GiamSatDichBenh-Server-Setup-v0.8.0.exe\n"

    def fake_urlopen(request, timeout=None):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        if url == um.GITHUB_LATEST_RELEASE_API:
            return _FakeResponse(release_body)
        if url == "https://example.test/SHA256SUMS.txt":
            return _FakeResponse(sums_body)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(um.urllib.request, "urlopen", fake_urlopen)
    info = um.fetch_github_release("server")
    assert info.version == "0.8.0"
    assert info.asset_name == "GiamSatDichBenh-Server-Setup-v0.8.0.exe"
    assert info.download_url == "https://example.test/Server-Setup.exe"
    assert info.sha256 == "deadbeef" * 8
    assert info.notes == "Ghi chú phát hành"


def test_fetch_github_release_unknown_mode():
    with pytest.raises(um.UpdateError):
        um.fetch_github_release("bogus-mode")


def test_fetch_github_release_missing_asset(monkeypatch):
    release_body = json.dumps({"tag_name": "v0.8.0", "assets": []}).encode("utf-8")
    monkeypatch.setattr(um.urllib.request, "urlopen", lambda request, timeout=None: _FakeResponse(release_body))
    with pytest.raises(um.UpdateError):
        um.fetch_github_release("standalone")


def test_download_url_to_file(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        um.urllib.request, "urlopen",
        lambda request, timeout=None: _FakeResponse(b"binary-content", headers={"Content-Length": "14"}),
    )
    seen = []
    destination = tmp_path / "out" / "installer.exe"
    result = um.download_url_to_file("https://example.test/x.exe", destination, progress=lambda d, t: seen.append((d, t)))
    assert result == destination
    assert destination.read_bytes() == b"binary-content"
    assert seen and seen[-1] == (14, 14)


def test_launch_installer_and_exit_invokes_popen(monkeypatch, tmp_path: Path):
    installer = tmp_path / "GiamSatDichBenh-Setup-v0.8.0.exe"
    installer.write_bytes(b"stub")
    calls = []
    monkeypatch.setattr(um.subprocess, "Popen", lambda args, **kwargs: calls.append(args))
    um.launch_installer_and_exit(installer)
    assert calls and calls[0] == [str(installer.resolve())]
