"""`/cdc/xuat-du-lieu` — Giai đoạn 5 (xem TASKS.md): xuất Excel/CSV theo bộ lọc và xuất ca bệnh
chia theo xã qua Web, thay cho nút "Xuất dữ liệu"/"Xuất theo xã..." của máy trạm PyQt6. Tái dùng
nguyên `core.export_filtered_records`/`export_cases_by_commune` — router chỉ nhận tham số từ
form/querystring rồi trả file qua `FileResponse`, không viết lại logic xuất."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import core
import duplicate_config
from webapp import TEMPLATES_DIR, auth
from webapp.config import WebAppSettings
from webapp.dependencies import get_settings_dep, require_password_current, require_role
from webapp.services.export_files import file_download_response, make_temp_export_path

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)

CAN_EXPORT_ROLES = (core.CDC_ROLE_SUPER_ADMIN, core.CDC_ROLE_ADMIN, core.CDC_ROLE_DATA_OPERATOR)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


@router.get("/cdc/xuat-du-lieu", response_class=HTMLResponse)
def export_hub(
    request: Request, err: str = "",
    user: auth.CurrentUser = Depends(require_password_current),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    case_criteria = duplicate_config.load_case_criteria()
    criteria_text = ", ".join(duplicate_config.CASE_CRITERIA_LABELS.get(c, c) for c in case_criteria.enabled)
    token = auth.get_csrf_token(request)
    response = templates.TemplateResponse(request, "export.html", {
        "user": user, "csrf_token": token, "active": "xuat-du-lieu",
        "can_export": user.has_role(*CAN_EXPORT_ROLES), "criteria_text": criteria_text, "err": err,
    })
    auth.set_csrf_cookie(response, request, token)
    return response


@router.get("/cdc/xuat-du-lieu/tai-ve")
def export_filtered(
    entity: str = "case", search: str = "", disease: str = "", status: str = "", admin_area: str = "", fmt: str = "xlsx",
    user: auth.CurrentUser = Depends(require_role(*CAN_EXPORT_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    entity_type = entity if entity in ("case", "outbreak") else "case"
    suffix = ".csv" if fmt == "csv" else ".xlsx"
    tmp_path = make_temp_export_path(suffix)
    try:
        core.export_filtered_records(
            tmp_path, entity_type, search=search, disease=disease, status=status, admin_area=admin_area,
            db_path=settings.db_path,
        )
    except ValueError as exc:
        tmp_path.unlink(missing_ok=True)
        return RedirectResponse(f"/cdc/xuat-du-lieu?err={quote(str(exc))}", status_code=303)
    prefix = "ca_benh" if entity_type == "case" else "o_dich"
    return file_download_response(tmp_path, f"{prefix}_{_timestamp()}{suffix}")


@router.get("/cdc/xuat-du-lieu/theo-xa")
def export_by_commune(
    user: auth.CurrentUser = Depends(require_role(*CAN_EXPORT_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    tmp_path = make_temp_export_path(".xlsx")
    criteria = duplicate_config.load_case_criteria()
    try:
        core.export_cases_by_commune(tmp_path, criteria=criteria, db_path=settings.db_path, actor=user.username)
    except ValueError as exc:
        tmp_path.unlink(missing_ok=True)
        return RedirectResponse(f"/cdc/xuat-du-lieu?err={quote(str(exc))}", status_code=303)
    return file_download_response(tmp_path, f"ca_benh_theo_xa_{_timestamp()}.xlsx")
