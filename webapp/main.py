"""FastAPI app — Web App quản trị tập trung, thay cho máy trạm PyQt6. Xem TASKS.md (nhiệm vụ
chuyển ứng dụng sang Web App) và CLAUDE.md. Chạy dev: `uvicorn webapp.main:app --reload`."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import core
import deployment_config
import ha_sync
from webapp import STATIC_DIR, TEMPLATES_DIR, scheduler
from webapp.dependencies import ForbiddenError, RedirectException
from webapp.routers import (
    accounts, audit_log, backups, dashboard, dedup, ha, import_history, login, queue, records,
    settings, submission_api, xuat_du_lieu,
)

# Origin duy nhất của trang GitHub Pages nộp báo cáo (docs/index.html) — CHỈ origin này được
# phép gọi thẳng POST /queue/submit-xa từ trình duyệt (xem webapp/routers/submission_api.py).
# `allow_credentials=False` (mặc định) là chủ đích: request cross-origin sẽ KHÔNG kèm cookie
# `cdc_session`/`csrf_token`, nên dù CORSMiddleware áp dụng toàn app, các route đăng nhập bằng
# cookie (/cdc/...) không lộ dữ liệu qua origin khác — chỉ /queue/submit-xa (tự xác thực bằng
# header X-GSBTN-Password, không dùng cookie) thật sự cần cross-origin.
PUBLIC_FRONTEND_ORIGIN = "https://cdc-hp.github.io"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Kiểm tra 1 lần lúc khởi động: nếu máy này vừa bật lại sau sự cố (vd mất điện) mà cấu hình
    # cũ trên đĩa vẫn ghi "primary", trong khi máy kia đã được thăng cấp làm chính lúc máy này
    # vắng mặt — tự hạ cấp để tránh "song chính" (xem ha_sync.resolve_startup_conflict và
    # CLAUDE.md mục "Máy chủ dự phòng"). Không phải health-check định kỳ nên không gây flapping.
    ha_sync.resolve_startup_conflict()
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="Giám sát dịch bệnh — CDC Hải Phòng", docs_url=None, redoc_url=None, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[PUBLIC_FRONTEND_ORIGIN],
    allow_methods=["POST"],
    allow_headers=["Content-Type", "X-GSBTN-Password"],
    allow_credentials=False,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(login.router)
app.include_router(dashboard.router)
app.include_router(queue.router)
app.include_router(records.router)
app.include_router(import_history.router)
app.include_router(dedup.router)
app.include_router(xuat_du_lieu.router)
app.include_router(accounts.router)
app.include_router(audit_log.router)
app.include_router(backups.router)
app.include_router(settings.router)
app.include_router(submission_api.router)
app.include_router(ha.router)

_error_templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Path luôn được phép ghi dù máy đang ở vai trò "dự phòng" (xem CLAUDE.md mục "Máy chủ dự
# phòng"): đăng nhập/đổi mật khẩu/thiết lập lần đầu, trang cấu hình (để admin còn thăng/hạ cấp
# và chỉnh peer_server_url/peer_shared_key được), và mọi endpoint máy-tới-máy (để máy kia luôn
# báo hạ cấp/kéo snapshot được bất kể vai trò máy này).
_HA_WRITE_ALLOWLIST_PREFIXES = (
    "/cdc/login", "/cdc/logout", "/cdc/change-password", "/cdc/setup",
    "/cdc/cau-hinh", "/cdc/vai-tro-may-chu", "/noi-bo/ha/",
)
_HA_STANDBY_MESSAGE = (
    "Máy này đang ở chế độ dự phòng — không nhận thay đổi dữ liệu. "
    "Vào Cấu hình để đặt máy chính nếu cần."
)


@app.middleware("http")
async def _block_writes_when_standby(request: Request, call_next):
    """Chặn MỌI request ghi dữ liệu (POST/PUT/PATCH/DELETE) khi máy đang ở vai trò "dự phòng"
    (`server_role == "standby"`) — Cloudflare Tunnel Replica cân bằng tải giữa mọi máy đang kết
    nối, không tự ưu tiên máy chính, nên bản thân app phải tự chặn để tránh xã/quản trị viên vô
    tình ghi trúng máy dự phòng (dữ liệu đó sẽ bị mất khi máy dự phòng đồng bộ đè lại từ máy
    chính ở lần kéo kế tiếp). Middleware duy nhất, chặn mặc định + allowlist, thay vì sửa từng
    router ghi dữ liệu — giảm rủi ro bỏ sót 1 route khi thêm tính năng mới sau này."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        path = request.url.path
        if not path.startswith(_HA_WRITE_ALLOWLIST_PREFIXES):
            if deployment_config.load_config().server_role == "standby":
                if path.startswith("/queue/"):
                    return JSONResponse({"ok": False, "error": _HA_STANDBY_MESSAGE}, status_code=409)
                return _error_templates.TemplateResponse(
                    request, "error.html",
                    {"code": 409, "title": "Máy dự phòng", "message": _HA_STANDBY_MESSAGE},
                    status_code=409,
                )
    return await call_next(request)


@app.exception_handler(RedirectException)
async def _handle_redirect(request: Request, exc: RedirectException):
    return RedirectResponse(exc.location, status_code=303)


@app.exception_handler(ForbiddenError)
async def _handle_forbidden(request: Request, exc: ForbiddenError):
    return _error_templates.TemplateResponse(
        request, "error.html", {"code": 403, "title": "Không đủ quyền", "message": str(exc)}, status_code=403,
    )


@app.get("/")
def root():
    return RedirectResponse("/cdc/login", status_code=303)


@app.get("/health")
def health():
    """Section 11 — kiểm tra nhanh service còn sống + kết nối được CSDL hay không, dùng cho
    Windows Service giám sát và cho việc kiểm tra sau khi cài đặt."""
    try:
        core.init_db(core.DB_PATH)
        database_ok = True
    except Exception:
        database_ok = False
    status = scheduler.get_status()
    if not status["scheduler_running"]:
        scheduler_state = "chua_chay"
    elif status["running"]:
        scheduler_state = "dang_dong_bo"
    else:
        scheduler_state = "dang_chay"
    return {
        "status": "ok" if database_ok else "error",
        "version": core.VERSION,
        "database": "ok" if database_ok else "loi",
        "scheduler": scheduler_state,
    }
