"""`/cdc/ca-benh` và `/cdc/o-dich` — Section 6 của nhiệm vụ Web App (xem TASKS.md Giai đoạn 4).
Dùng chung 1 router cho cả 2 loại bản ghi vì cấu trúc giống hệt nhau ("Ổ dịch có chức năng
tương tự danh sách ca bệnh") — chỉ khác tập cột và nhãn trường."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import core
from webapp import auth
from webapp.config import WebAppSettings
from webapp.dependencies import ForbiddenError, get_settings_dep, require_password_current
from webapp.routers.xuat_du_lieu import CAN_EXPORT_ROLES

router = APIRouter()
templates = Jinja2Templates(directory="webapp/templates")

CASE_LIST_COLUMNS = [
    ("case_code", "Mã số"), ("full_name", "Họ tên"), ("birth_date_raw", "Ngày sinh"),
    ("gender", "Giới"), ("commune", "Xã/Phường"), ("main_diagnosis", "Chẩn đoán"),
    ("onset_date", "Khởi phát"), ("current_status", "Tình trạng"), ("reporting_unit", "Đơn vị báo cáo"),
]
OUTBREAK_LIST_COLUMNS = [
    ("disease", "Tên bệnh"), ("location", "Địa điểm"), ("first_onset_date", "Khởi phát"),
    ("status", "Trạng thái"), ("case_count", "Số ca mắc"), ("death_count", "Tử vong"),
    ("reporting_unit", "Đơn vị báo cáo"),
]

ENTITY_CONFIG = {
    "case": {
        "path": "ca-benh", "title": "Ca bệnh", "list_columns": CASE_LIST_COLUMNS,
        "labels": core.CASE_LABELS, "active": "ca-benh",
    },
    "outbreak": {
        "path": "o-dich", "title": "Ổ dịch", "list_columns": OUTBREAK_LIST_COLUMNS,
        "labels": core.OUTBREAK_LABELS, "active": "o-dich",
    },
}


def _list_view(entity_type: str):
    meta = ENTITY_CONFIG[entity_type]

    def _view(
        request: Request,
        search: str = "", disease: str = "", status: str = "", admin_area: str = "", page: int = 1,
        user: auth.CurrentUser = Depends(require_password_current),
        settings: WebAppSettings = Depends(get_settings_dep),
    ):
        page = max(1, page)
        rows, total = core.query_records(
            entity_type, search=search, disease=disease, status=status, admin_area=admin_area,
            page=page, page_size=50, db_path=settings.db_path,
        )
        page_size = 50
        total_pages = max(1, (total + page_size - 1) // page_size)
        disease_field = "main_diagnosis" if entity_type == "case" else "disease"
        area_field = "commune" if entity_type == "case" else "admin_area"
        disease_options = core.list_filter_values(entity_type, disease_field, db_path=settings.db_path)
        area_options = core.list_filter_values(entity_type, area_field, db_path=settings.db_path)

        token = auth.get_csrf_token(request)
        response = templates.TemplateResponse(request, "records_list.html", {
            "user": user, "csrf_token": token, "active": meta["active"],
            "entity_type": entity_type, "entity_path": meta["path"], "title": meta["title"],
            "columns": meta["list_columns"], "rows": rows, "total": total,
            "page": page, "total_pages": total_pages,
            "filters": {"search": search, "disease": disease, "status": status, "admin_area": admin_area},
            "disease_options": disease_options, "area_options": area_options,
            "area_label": "Xã/Phường" if entity_type == "case" else "Địa bàn",
            "disease_label": "Chẩn đoán" if entity_type == "case" else "Tên bệnh",
            "can_export": user.has_role(*CAN_EXPORT_ROLES),
        })
        auth.set_csrf_cookie(response, request, token)
        return response

    return _view


def _detail_view(entity_type: str):
    meta = ENTITY_CONFIG[entity_type]

    def _view(
        record_id: int, request: Request,
        user: auth.CurrentUser = Depends(require_password_current),
        settings: WebAppSettings = Depends(get_settings_dep),
    ):
        record = core.get_record(entity_type, record_id, db_path=settings.db_path)
        if not record:
            raise ForbiddenError("Không tìm thấy bản ghi.")
        issues = core.list_quality_issues(entity_type=entity_type, entity_id=record_id, db_path=settings.db_path)
        fields = [(meta["labels"].get(key, key), key, value) for key, value in record.items() if key not in ("raw_json",)]

        token = auth.get_csrf_token(request)
        response = templates.TemplateResponse(request, "record_detail.html", {
            "user": user, "csrf_token": token, "active": meta["active"],
            "entity_type": entity_type, "entity_path": meta["path"], "title": meta["title"],
            "record": record, "fields": fields, "issues": issues,
        })
        auth.set_csrf_cookie(response, request, token)
        return response

    return _view


router.add_api_route("/cdc/ca-benh", _list_view("case"), methods=["GET"], response_class=HTMLResponse)
router.add_api_route("/cdc/ca-benh/{record_id}", _detail_view("case"), methods=["GET"], response_class=HTMLResponse)
router.add_api_route("/cdc/o-dich", _list_view("outbreak"), methods=["GET"], response_class=HTMLResponse)
router.add_api_route("/cdc/o-dich/{record_id}", _detail_view("outbreak"), methods=["GET"], response_class=HTMLResponse)
