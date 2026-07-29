"""Trang xem (chỉ đọc) ca bệnh/ổ dịch dành cho tài khoản xã — `/xa/ca-benh`, `/xa/o-dich`.

**Ranh giới bảo mật cốt lõi**: mọi truy vấn LUÔN tự gán `admin_area = <xã đang đăng nhập>` ở
phía server, bỏ qua hoàn toàn mọi giá trị từ query string — không dùng lại
`webapp/routers/records.py::_list_view` (thiết kế cho CDC, nhận `admin_area` trực tiếp từ query
param của trình duyệt, không phù hợp làm ranh giới quyền cho xã)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import core
from webapp import TEMPLATES_DIR, auth, commune_auth
from webapp.config import WebAppSettings
from webapp.dependencies import ForbiddenError, get_settings_dep, require_commune_login
from webapp.routers.records import CASE_DEFAULT_VISIBLE_COLUMNS, CASE_LIST_COLUMNS, OUTBREAK_LIST_COLUMNS
from webapp.services import records_query

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)

ENTITY_CONFIG = {
    "case": {"path": "ca-benh", "title": "Ca bệnh", "list_columns": CASE_LIST_COLUMNS, "labels": core.CASE_LABELS, "area_field": "commune"},
    "outbreak": {"path": "o-dich", "title": "Ổ dịch", "list_columns": OUTBREAK_LIST_COLUMNS, "labels": core.OUTBREAK_LABELS, "area_field": "admin_area"},
}


@router.get("/xa", response_class=HTMLResponse)
@router.get("/xa/", response_class=HTMLResponse)
def home(_user: commune_auth.CommuneCurrentUser = Depends(require_commune_login)):
    return RedirectResponse("/xa/ca-benh", status_code=303)


def _list_view(entity_type: str):
    meta = ENTITY_CONFIG[entity_type]

    def _view(
        request: Request, search: str = "", page: int = 1,
        user: commune_auth.CommuneCurrentUser = Depends(require_commune_login),
        settings: WebAppSettings = Depends(get_settings_dep),
    ):
        page = max(1, page)
        page_size = 50
        if entity_type == "case":
            rows, total = records_query.query_cases(
                search=search, admin_area=user.commune, page=page, page_size=page_size, db_path=settings.db_path,
            )
        else:
            rows, total = core.query_records(
                "outbreak", search=search, admin_area=user.commune, page=page, page_size=page_size,
                db_path=settings.db_path,
            )
        total_pages = max(1, (total + page_size - 1) // page_size)
        token = auth.get_csrf_token(request)
        response = templates.TemplateResponse(request, "xa_records_list.html", {
            "user": user, "csrf_token": token,
            "entity_type": entity_type, "entity_path": meta["path"], "title": meta["title"],
            "columns": meta["list_columns"], "rows": rows, "total": total,
            "default_visible_columns": CASE_DEFAULT_VISIBLE_COLUMNS if entity_type == "case" else set(),
            "column_count": len(meta["list_columns"]),
            "page": page, "total_pages": total_pages, "search": search,
        })
        auth.set_csrf_cookie(response, request, token)
        return response

    return _view


def _detail_view(entity_type: str):
    meta = ENTITY_CONFIG[entity_type]

    def _view(
        record_id: int, request: Request,
        user: commune_auth.CommuneCurrentUser = Depends(require_commune_login),
        settings: WebAppSettings = Depends(get_settings_dep),
    ):
        record = core.get_record(entity_type, record_id, db_path=settings.db_path)
        # Không tiết lộ là bản ghi có tồn tại thuộc xã khác — coi như không tìm thấy nếu không
        # đúng xã đang đăng nhập (đúng mẫu ForbiddenError đã dùng cho "không tìm thấy" ở
        # webapp/routers/records.py::_detail_view).
        if not record or record.get(meta["area_field"]) != user.commune:
            raise ForbiddenError("Không tìm thấy bản ghi.")
        fields = [(meta["labels"].get(key, key), key, value) for key, value in record.items() if key not in ("raw_json",)]
        token = auth.get_csrf_token(request)
        response = templates.TemplateResponse(request, "xa_record_detail.html", {
            "user": user, "csrf_token": token,
            "entity_type": entity_type, "entity_path": meta["path"], "title": meta["title"],
            "record": record, "fields": fields,
        })
        auth.set_csrf_cookie(response, request, token)
        return response

    return _view


router.add_api_route("/xa/ca-benh", _list_view("case"), methods=["GET"], response_class=HTMLResponse)
router.add_api_route("/xa/ca-benh/{record_id}", _detail_view("case"), methods=["GET"], response_class=HTMLResponse)
router.add_api_route("/xa/o-dich", _list_view("outbreak"), methods=["GET"], response_class=HTMLResponse)
router.add_api_route("/xa/o-dich/{record_id}", _detail_view("outbreak"), methods=["GET"], response_class=HTMLResponse)
