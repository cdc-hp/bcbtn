from __future__ import annotations

import json
import os
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path


def _user_data_root() -> Path:
    override = os.environ.get("GIAM_SAT_DICH_BENH_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "CDC_HaiPhong" / "GiamSatDichBenh"
    return Path.home() / ".giam_sat_dich_benh"


CONFIG_PATH = _user_data_root() / "deployment.json"


@dataclass
class DeploymentConfig:
    server_host: str = "0.0.0.0"
    server_port: int = 8765
    secondary_webapp_url: str = ""
    secondary_shared_key: str = ""
    secondary_sync_interval_minutes: int = 20
    # Khoá riêng cho Google Apps Script gọi POST /queue/submit trên webapp/ (Web App tập
    # trung) — TÁCH RIÊNG khỏi `public_submit_key` để giới hạn phạm vi nếu lộ và đổi được độc
    # lập. Header vẫn là X-GSBTN-Password (không đổi phía Code.gs) — chỉ khác giá trị nào được
    # server đem ra so khớp. Xem webapp/routers/submission_api.py.
    gas_api_key: str = ""
    # Khoá riêng cho POST /queue/submit-xa — nơi trang GitHub Pages (docs/index.html) nộp TRỰC
    # TIẾP từ trình duyệt của xã (không qua Google Apps Script nữa khi máy chủ chính online).
    # TÁCH RIÊNG khỏi `gas_api_key` vì khác hẳn về mức độ lộ: `gas_api_key` chỉ truyền giữa 2 máy
    # chủ (Apps Script -> máy chủ chính, không lộ ra trình duyệt); khoá này thì mọi xã đều gõ vào
    # form công khai mỗi lần nộp (giống hệt ô "Khóa máy chủ phụ" hiện có trên trang GAS) nên coi
    # là bí mật dùng chung (không phải bí mật cấp máy chủ) — CDC có thể đặt TRÙNG giá trị với
    # SHARED_KEY bên Google Apps Script để xã chỉ cần nhớ/gõ một khoá duy nhất cho cả 2 đường nộp.
    public_submit_key: str = ""
    web_token_secret: str = ""
    # Địa chỉ Internet công khai của máy chủ này (vd. qua Cloudflare Tunnel), dùng để tự kiểm tra
    # kết nối ra ngoài và điền vào MAIN_SERVER_URL của Google Apps Script.
    public_url: str = ""
    # Giữ máy không vào chế độ ngủ trong lúc server đang chạy (không giữ màn hình sáng) — dùng
    # bởi service_tray.py khi chạy chế độ thủ công (thu vào khay hệ thống thay vì dịch vụ Windows).
    prevent_sleep: bool = False
    # Máy chủ dự phòng (failover thủ công, xem ha_sync.py) — KHÔNG liên quan "máy chủ phụ" Google
    # Apps Script ở trên (secondary_*), đó là đệm nộp báo cáo, còn đây là 1 bản cài Web App khác
    # của CHÍNH ứng dụng này, cùng public qua Cloudflare Tunnel Replica. "primary" = đang phục vụ
    # ghi dữ liệu thật; "standby" = chỉ đọc, tự kéo bản sao CSDL định kỳ từ máy chính.
    server_role: str = "primary"
    # Địa chỉ CÔNG KHAI của máy kia qua tên miền Cloudflare Tunnel RIÊNG của máy đó (vd
    # "https://may2.cdc-hp.io.vn") — KHÔNG phải IP LAN: máy dự phòng đặt ở nơi khác (khác điện/
    # mạng với máy chính, mới bảo vệ được đúng loại sự cố mất điện/Internet tại chỗ), nên 2 máy
    # chỉ nói chuyện được qua Internet. Mỗi máy cần 1 tunnel/tên miền phụ RIÊNG chỉ để gọi máy-
    # tới-máy (khác tunnel dùng chung phục vụ cdc-hp.io.vn, vì Cloudflare Tunnel Replica cân bằng
    # tải giữa các máy — không thể định tuyến TỚI ĐÚNG 1 máy cụ thể qua tên miền dùng chung). Dùng
    # cả 2 chiều: máy dự phòng gọi sang để kéo snapshot, máy vừa được thăng cấp gọi sang để báo
    # máy kia tự hạ cấp. Xem CLAUDE.md mục "Máy chủ dự phòng".
    peer_server_url: str = ""
    # Khoá riêng cho gọi máy-tới-máy (kéo snapshot CSDL + báo hạ cấp) — TÁCH RIÊNG khỏi
    # gas_api_key/public_submit_key/secondary_shared_key vì khác trust boundary (khoá này cho
    # phép đọc toàn bộ CSDL qua /noi-bo/ha/snapshot, không phải chỉ nộp 1 file như các khoá kia).
    # Vì endpoint này công khai ra Internet (không còn chỉ LAN nội bộ), NÊN đặt khoá dài/ngẫu
    # nhiên (`webapp/services/rate_limit.py::ha_peer_limiter` chỉ làm chậm dò khoá, không thay
    # được khoá yếu).
    peer_shared_key: str = ""
    standby_sync_interval_minutes: int = 15


def load_config() -> DeploymentConfig:
    if not CONFIG_PATH.exists():
        return DeploymentConfig()
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DeploymentConfig()
    try:
        port = int(raw.get("server_port", 8765))
    except (TypeError, ValueError):
        port = 8765
    port = max(1, min(65535, port))
    return DeploymentConfig(
        server_host=str(raw.get("server_host", "0.0.0.0") or "0.0.0.0").strip(),
        server_port=port,
        secondary_webapp_url=str(raw.get("secondary_webapp_url", "") or "").strip(),
        secondary_shared_key=str(raw.get("secondary_shared_key", "") or ""),
        secondary_sync_interval_minutes=max(5, min(180, int(raw.get("secondary_sync_interval_minutes", 20) or 20))),
        gas_api_key=str(raw.get("gas_api_key", "") or ""),
        public_submit_key=str(raw.get("public_submit_key", "") or ""),
        web_token_secret=str(raw.get("web_token_secret", "") or ""),
        public_url=str(raw.get("public_url", "") or "").strip().rstrip("/"),
        prevent_sleep=bool(raw.get("prevent_sleep", False)),
        server_role=str(raw.get("server_role", "primary") or "primary").strip() or "primary",
        peer_server_url=str(raw.get("peer_server_url", "") or "").strip().rstrip("/"),
        peer_shared_key=str(raw.get("peer_shared_key", "") or ""),
        standby_sync_interval_minutes=max(5, min(180, int(raw.get("standby_sync_interval_minutes", 15) or 15))),
    )


def save_config(config: DeploymentConfig) -> Path:
    config.server_port = max(1, min(65535, int(config.server_port)))
    config.secondary_sync_interval_minutes = max(5, min(180, int(config.secondary_sync_interval_minutes)))
    if config.server_role not in ("primary", "standby"):
        config.server_role = "primary"
    config.peer_server_url = config.peer_server_url.strip().rstrip("/")
    config.standby_sync_interval_minutes = max(5, min(180, int(config.standby_sync_interval_minutes)))
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = CONFIG_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(CONFIG_PATH)
    return CONFIG_PATH


def ensure_web_token_secret(config: DeploymentConfig) -> DeploymentConfig:
    """Sinh và lưu khóa ký phiên đăng nhập tài khoản xã nếu chưa có (chạy một lần)."""
    if not config.web_token_secret:
        config.web_token_secret = secrets.token_hex(32)
        save_config(config)
    return config
