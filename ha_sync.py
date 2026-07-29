"""Đồng bộ máy chủ dự phòng (failover thủ công) — KHÔNG liên quan "máy chủ phụ" Google Apps
Script (``secondary_sync.py``, đệm nộp báo cáo khi máy chính offline). Đây là đồng bộ giữa 2 bản
cài CÙNG ứng dụng này, đặt Ở NƠI KHÁC nhau (khác điện/mạng — mới bảo vệ được đúng loại sự cố
nghiêm trọng nhất: mất điện/Internet tại nơi đặt máy chính). Máy chính vẫn public qua Cloudflare
Tunnel Replica dùng chung (``cdc-hp.io.vn``) như bình thường; riêng gọi máy-tới-máy (module này)
đi qua tên miền Cloudflare Tunnel RIÊNG của TỪNG máy (mỗi máy 1 tunnel/tên miền phụ chỉ để 2 máy
gọi nhau) — xem CLAUDE.md mục "Máy chủ dự phòng" để biết lý do không thể dùng IP LAN hay tên miền
dùng chung cho việc này.

Chiều đồng bộ: máy đang ở vai trò "standby" định kỳ KÉO một bản sao gần như đầy đủ CSDL từ máy
đang ở vai trò "primary" (không đẩy ngược chiều nào — máy dự phòng không bao giờ là nguồn dữ
liệu). Tái dùng toàn bộ hạ tầng backup/restore đã có ở ``backup_manager.py`` thay vì viết lại:
snapshot phát ra từ máy chính chính là 1 bản backup nhất quán (``sqlite3 .backup()``), và áp dụng
vào máy dự phòng dùng lại ``backup_manager.restore_backup`` (đã tự sao lưu an toàn trước khi ghi
đè + tự phục hồi nếu lỗi).

Chỉ dùng thư viện chuẩn (``urllib``), giống ``secondary_sync.py``."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import backup_manager
import core
import deployment_config

# Cả 3 mốc thời gian đều rộng rãi hơn mức cần cho LAN nội bộ vì giờ đi qua Internet thật (2 máy ở
# 2 nơi khác nhau) — độ trễ/băng thông tải lên (đặc biệt lúc kéo snapshot CSDL, có thể vài chục MB)
# qua đường Internet của máy chính (không phải LAN tốc độ cao) chậm và biến thiên hơn nhiều.
DEFAULT_PULL_TIMEOUT = 180
DEFAULT_DEMOTE_TIMEOUT = 15
DEFAULT_ROLE_CHECK_TIMEOUT = 15
PEER_KEY_HEADER = "X-CDC-Peer-Key"
# User-Agent mặc định của urllib ("Python-urllib/3.x") bị nhiều WAF/"Bot Fight Mode" của
# Cloudflare chặn thẳng bằng HTTP 403 trước khi request kịp tới app (lỗi thật gặp phải: đồng bộ
# báo lỗi 403 dù key đúng, app còn chưa kịp xử lý request). Đặt User-Agent riêng để CDC dễ thêm
# ngoại lệ WAF cho đúng traffic máy-tới-máy này (xem CLAUDE.md mục "Máy chủ dự phòng").
_REQUEST_HEADERS_BASE = {"User-Agent": "CDC-GiamSatDichBenh-HA/1.0 (may-toi-may, xem CLAUDE.md)"}


def _peer_headers(peer_key: str) -> dict[str, str]:
    return {**_REQUEST_HEADERS_BASE, PEER_KEY_HEADER: peer_key}


_run_lock = threading.Lock()
_state_lock = threading.Lock()
_state: dict[str, Any] = {
    "running": False, "last_run_at": "", "last_success_at": "", "last_result": None, "last_error": "",
}


def _set_state(**kwargs: Any) -> None:
    with _state_lock:
        _state.update(kwargs)


def get_status() -> dict[str, Any]:
    with _state_lock:
        status = dict(_state)
    config = deployment_config.load_config()
    status["server_role"] = config.server_role
    status["configured"] = bool(config.peer_server_url and config.peer_shared_key)
    status["interval_minutes"] = config.standby_sync_interval_minutes
    return status


def pull_snapshot_from_peer(peer_url: str, peer_key: str, timeout: int = DEFAULT_PULL_TIMEOUT) -> Path:
    """Kéo snapshot CSDL từ máy chính về file tạm, xác minh toàn vẹn trước khi trả về đường dẫn.

    Ném lỗi nếu máy kia từ chối (sai khoá, hoặc máy kia hiện KHÔNG phải máy chính) hoặc file tải
    về không đạt kiểm tra toàn vẹn — không bao giờ trả về 1 snapshot không đáng tin."""
    if not peer_url:
        raise ValueError("Chưa cấu hình địa chỉ máy kia (peer_server_url).")
    url = peer_url.rstrip("/") + "/noi-bo/ha/snapshot"
    request = Request(url, headers=_peer_headers(peer_key), method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            data = response.read()
    except HTTPError as exc:
        raise ConnectionError(f"Máy kia trả lỗi HTTP {exc.code} khi kéo snapshot.") from exc
    except URLError as exc:
        raise ConnectionError(f"Không kết nối được máy kia: {exc.reason}") from exc

    tmp_dir = backup_manager.USER_DATA_DIR / "ha_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"ha_pull_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.db"
    tmp_path.write_bytes(data)

    check = backup_manager.verify_backup(tmp_path)
    if not check["ok"]:
        tmp_path.unlink(missing_ok=True)
        raise ValueError(f"Snapshot tải về không đạt kiểm tra toàn vẹn: {check['message']}")
    return tmp_path


def apply_snapshot(snapshot_path: Path, db_path: str | None = None) -> dict[str, Any]:
    """Áp bản snapshot vào CSDL cục bộ — tái dùng backup_manager.restore_backup (đã tự sao lưu
    an toàn CSDL hiện tại trước khi ghi đè, tự phục hồi lại nếu bản mới lỗi)."""
    db_path = db_path or core.DB_PATH
    try:
        return backup_manager.restore_backup(snapshot_path, Path(db_path))
    finally:
        Path(snapshot_path).unlink(missing_ok=True)


def notify_peer_demote(peer_url: str, peer_key: str, timeout: int = DEFAULT_DEMOTE_TIMEOUT) -> bool:
    """Báo cho máy kia tự hạ cấp xuống dự phòng — cố gắng hết sức, không ném lỗi ra ngoài (gọi
    thất bại phải hiện cảnh báo rõ cho super-admin ở nơi gọi, không được âm thầm coi là thành
    công)."""
    if not peer_url:
        return False
    url = peer_url.rstrip("/") + "/noi-bo/ha/demote"
    request = Request(url, data=b"", headers=_peer_headers(peer_key), method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except (HTTPError, URLError):
        return False


def request_peer_sync_now(peer_url: str, peer_key: str, timeout: int = DEFAULT_PULL_TIMEOUT) -> dict[str, Any]:
    """Gọi SANG máy kia (đang là dự phòng) yêu cầu nó tự kéo snapshot NGAY — dùng bởi nút "Yêu
    cầu máy dự phòng đồng bộ ngay" trên máy chính, để không phải đợi tới chu kỳ định kỳ của máy
    dự phòng (vd trước khi tắt máy chính để bảo trì). Máy kia tự thực hiện việc kéo (chiều đồng bộ
    không đổi — máy chính không bao giờ đẩy dữ liệu, chỉ NHỜ máy kia tự kéo).

    `timeout` dùng `DEFAULT_PULL_TIMEOUT` (không phải `DEFAULT_ROLE_CHECK_TIMEOUT`) vì request này
    CHỜ máy kia kéo xong toàn bộ snapshot trước khi trả lời — cùng độ dài với việc tự kéo trực
    tiếp, không phải 1 lượt hỏi nhanh như `check_peer_role`."""
    if not peer_url:
        return {"ok": False, "error": "Chưa cấu hình địa chỉ máy kia (peer_server_url)."}
    url = peer_url.rstrip("/") + "/noi-bo/ha/yeu-cau-dong-bo"
    request = Request(url, data=b"", headers=_peer_headers(peer_key), method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload if isinstance(payload, dict) else {"ok": False, "error": "Phản hồi không hợp lệ."}
    except HTTPError as exc:
        return {"ok": False, "error": f"Máy kia trả lỗi HTTP {exc.code}."}
    except URLError as exc:
        return {"ok": False, "error": f"Không kết nối được máy kia: {exc.reason}"}
    except (ValueError, TypeError):
        return {"ok": False, "error": "Phản hồi từ máy kia không đọc được (không phải JSON hợp lệ)."}


def run_standby_pull_once(db_path: str | None = None) -> dict[str, Any]:
    """Chạy 1 lần kéo snapshot từ máy chính; bỏ qua im lặng (có lý do rõ) nếu máy này không phải
    dự phòng, chưa cấu hình máy kia, hoặc đang có lần chạy khác. Dùng chung cho cả tác vụ định kỳ
    lẫn nút "Đồng bộ ngay"."""
    if not _run_lock.acquire(blocking=False):
        return {"skipped": True, "reason": "Đang có lần đồng bộ khác đang chạy."}
    resolved_db_path = db_path or core.DB_PATH
    try:
        _set_state(running=True)
        config = deployment_config.load_config()
        if config.server_role != "standby":
            return {"skipped": True, "reason": "Máy này hiện không phải máy dự phòng."}
        if not (config.peer_server_url and config.peer_shared_key):
            return {"skipped": True, "reason": "Chưa cấu hình máy kia (peer_server_url/peer_shared_key)."}
        now = datetime.now().isoformat(sep=" ", timespec="seconds")
        try:
            snapshot_path = pull_snapshot_from_peer(config.peer_server_url, config.peer_shared_key)
            result = apply_snapshot(snapshot_path, db_path=resolved_db_path)
            _set_state(last_run_at=now, last_success_at=now, last_result=result, last_error="")
            core.log_audit("ha_standby_pull", actor="he_thong", db_path=resolved_db_path)
            return result
        except Exception as exc:
            _set_state(last_run_at=now, last_error=str(exc))
            core.log_audit("ha_standby_pull_error", actor="he_thong", detail=str(exc), db_path=resolved_db_path)
            return {"error": str(exc)}
    finally:
        _set_state(running=False)
        _run_lock.release()


def check_peer_role(peer_url: str, peer_key: str, timeout: int = DEFAULT_ROLE_CHECK_TIMEOUT) -> str | None:
    """Hỏi vai trò hiện tại của máy kia — dùng lúc khởi động để phát hiện xung đột "song chính".
    Trả None nếu không hỏi được (mất mạng, sai khoá, máy kia chưa lên...) — im lặng bỏ qua, đây
    chỉ là kiểm tra phòng ngừa, không phải luồng chính."""
    if not peer_url:
        return None
    url = peer_url.rstrip("/") + "/noi-bo/ha/vai-tro"
    request = Request(url, headers=_peer_headers(peer_key), method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return str(payload.get("server_role", "")) or None
    except (HTTPError, URLError, ValueError, TypeError):
        return None


def resolve_startup_conflict(db_path: str | None = None) -> dict[str, Any]:
    """Chạy ĐÚNG 1 LẦN lúc khởi động dịch vụ (xem `webapp/main.py::lifespan`) — KHÔNG phải
    health-check định kỳ, nên không tạo rủi ro tự động chuyển đổi qua lại (flapping) khi mất
    mạng tạm thời như lo ngại ban đầu về failover tự động.

    Xử lý đúng 1 kịch bản: máy này vừa khởi động lại (vd sau mất điện) và cấu hình cũ trên đĩa
    vẫn ghi "primary" — vì không có gì trên máy này biết được lúc nó vắng mặt, máy kia đã được
    con người thăng cấp làm chính hay chưa. Nếu hỏi máy kia và thấy máy kia CŨNG đang là chính,
    máy kia đáng tin hơn (vai trò đó phản ánh 1 hành động thật gần đây của super-admin) — máy này
    tự nhường, hạ cấp mình xuống dự phòng NGAY, rồi lập tức kéo bù 1 lần snapshot mới nhất từ máy
    kia (không đợi tới chu kỳ đồng bộ định kỳ tiếp theo, có thể xa tới
    `standby_sync_interval_minutes`) — máy này càng sớm có đủ dữ liệu đã ghi trong lúc nó tắt
    càng tốt. Sau khi kéo bù xong, máy này VẪN Ở LẠI vai trò dự phòng — KHÔNG tự động giành lại
    làm chính (đã xác nhận chủ đích với CDC: chuyển đổi luôn phải do super-admin bấm tay, kể cả
    khi máy chính cũ đã sẵn sàng trở lại, để tránh giành qua giành lại nếu máy đó hay khởi động
    lại/mất điện thường xuyên).

    Trường hợp cả 2 máy cùng khởi động lại đồng thời (vd cùng mất điện rồi cùng có điện lại) và
    cùng hỏi nhau cùng lúc: có thể cả 2 cùng thấy máy kia đang "primary" (do chưa ai kịp tự hạ cấp
    tại thời điểm hỏi) → CẢ 2 cùng tự hạ cấp, tạm thời không còn máy nào là chính. Đây là kết quả
    an toàn hơn (không phục vụ tạm thời) so với 2 máy cùng nhận ghi dữ liệu — super-admin chỉ cần
    vào 1 trong 2 máy bấm lại "Đặt máy này làm máy chính"."""
    config = deployment_config.load_config()
    if config.server_role != "primary":
        return {"skipped": True, "reason": "Máy này không phải máy chính, không cần kiểm tra."}
    if not (config.peer_server_url and config.peer_shared_key):
        return {"skipped": True, "reason": "Chưa cấu hình máy kia (peer_server_url/peer_shared_key)."}
    peer_role = check_peer_role(config.peer_server_url, config.peer_shared_key)
    if peer_role != "primary":
        return {"skipped": True, "reason": f"Máy kia không phải máy chính lúc kiểm tra (role={peer_role!r})."}
    config.server_role = "standby"
    deployment_config.save_config(config)
    core.log_audit(
        "ha_startup_self_demoted", actor="he_thong",
        detail="Phát hiện máy kia cũng đang là máy chính lúc khởi động — tự hạ cấp để tránh song chính.",
        db_path=db_path or core.DB_PATH,
    )
    catch_up = run_standby_pull_once(db_path=db_path)
    return {"demoted": True, "catch_up": catch_up}
