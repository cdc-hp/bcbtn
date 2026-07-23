"""FastAPI app — Web App quản trị tập trung, thay cho máy trạm PyQt6. Xem TASKS.md (nhiệm vụ
chuyển ứng dụng sang Web App) và CLAUDE.md. Chạy dev: `uvicorn webapp.main:app --reload`."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import core
from webapp.dependencies import ForbiddenError, RedirectException
from webapp.routers import (
    accounts, audit_log, backups, dashboard, dedup, login, queue, records, submission_api, xuat_du_lieu,
)

app = FastAPI(title="Giám sát dịch bệnh — CDC Hải Phòng", docs_url=None, redoc_url=None)

app.mount("/static", StaticFiles(directory="webapp/static"), name="static")
app.include_router(login.router)
app.include_router(dashboard.router)
app.include_router(queue.router)
app.include_router(records.router)
app.include_router(dedup.router)
app.include_router(xuat_du_lieu.router)
app.include_router(accounts.router)
app.include_router(audit_log.router)
app.include_router(backups.router)
app.include_router(submission_api.router)

_error_templates = Jinja2Templates(directory="webapp/templates")


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
    return {
        "status": "ok" if database_ok else "error",
        "version": core.VERSION,
        "database": "ok" if database_ok else "loi",
        "scheduler": "chua_trien_khai",
    }
