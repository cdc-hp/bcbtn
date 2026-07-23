"""Cấu hình Web App — bọc quanh deployment_config.py hiện có (dùng chung 1 file
deployment.json với ứng dụng desktop trong giai đoạn chuyển tiếp) thay vì tạo hệ cấu hình
riêng. Xem CLAUDE.md mục "Kiến trúc tổng thể" và TASKS.md nhiệm vụ chuyển sang Web App."""

from __future__ import annotations

from dataclasses import dataclass

import core
from deployment_config import DeploymentConfig, ensure_web_token_secret, load_config

SESSION_COOKIE_NAME = "cdc_session"
CSRF_COOKIE_NAME = "csrf_token"
SESSION_TTL_SECONDS = 8 * 3600


@dataclass
class WebAppSettings:
    config: DeploymentConfig
    db_path: str

    @property
    def session_secret(self) -> str:
        return self.config.web_token_secret


def get_settings() -> WebAppSettings:
    config = ensure_web_token_secret(load_config())
    return WebAppSettings(config=config, db_path=str(core.DB_PATH))
