"""`/cdc/ca-benh` và `/cdc/o-dich` — Section 6 của nhiệm vụ Web App (xem TASKS.md Giai đoạn 4).
Dùng chung 1 router cho cả 2 loại bản ghi vì cấu trúc giống hệt nhau ("Ổ dịch có chức năng
tương tự danh sách ca bệnh") — chỉ khác tập cột và nhãn trường."""

from __future__ import annotations

from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import core
from webapp import TEMPLATES_DIR, auth
from webapp.config import WebAppSettings
from webapp.dependencies import ForbiddenError, get_settings_dep, require_password_current, require_role
from webapp.routers.xuat_du_lieu import CAN_EXPORT_ROLES
from webapp.services import records_query

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)
CAN_EDIT_OUTBREAK_ROLES = (core.CDC_ROLE_SUPER_ADMIN, core.CDC_ROLE_ADMIN, core.CDC_ROLE_DATA_OPERATOR)
CAN_DELETE_OUTBREAK_ROLES = (core.CDC_ROLE_SUPER_ADMIN, core.CDC_ROLE_ADMIN)
# Ca bệnh có CCCD/SĐT — chỉ super_admin/admin được xóa hẳn, giống quyền xóa ổ dịch (không cho
# data_operator dù được nhập/sửa dữ liệu, khớp nguyên tắc "thao tác rủi ro cao" trong CLAUDE.md).
CAN_DELETE_CASE_ROLES = (core.CDC_ROLE_SUPER_ADMIN, core.CDC_ROLE_ADMIN)

CASE_LIST_COLUMNS = [(key, label) for label, key in core.CASE_FIELDS]
CASE_DEFAULT_VISIBLE_COLUMNS = {
    "case_code", "full_name", "birth_date_raw", "gender", "commune", "main_diagnosis",
    "onset_date", "current_status", "reporting_unit",
}
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
        sort: str = "", direction: str = "desc",
        user: auth.CurrentUser = Depends(require_password_current),
        settings: WebAppSettings = Depends(get_settings_dep),
    ):
        page = max(1, page)
        advanced_filters = records_query.clean_case_filters(request.query_params) if entity_type == "case" else {}
        if entity_type == "case":
            rows, total = records_query.query_cases(
                search=search, disease=disease, status=status, admin_area=admin_area,
                advanced=advanced_filters, page=page, page_size=50, sort=sort, direction=direction,
                db_path=settings.db_path,
            )
            advanced_options = records_query.list_case_options(settings.db_path)
        else:
            rows, total = core.query_records(
                entity_type, search=search, disease=disease, status=status, admin_area=admin_area,
                page=page, page_size=50, db_path=settings.db_path,
            )
            advanced_options = {}
        page_size = 50
        total_pages = max(1, (total + page_size - 1) // page_size)
        disease_field = "main_diagnosis" if entity_type == "case" else "disease"
        area_field = "commune" if entity_type == "case" else "admin_area"
        disease_options = core.list_filter_values(entity_type, disease_field, db_path=settings.db_path)
        area_options = core.list_filter_values(entity_type, area_field, db_path=settings.db_path)
        status_fields = ("record_status", "current_status") if entity_type == "case" else ("status",)
        status_options = sorted({
            value for field in status_fields
            for value in core.list_filter_values(entity_type, field, db_path=settings.db_path)
        })
        all_filters = {
            "search": search, "disease": disease, "status": status, "admin_area": admin_area,
            **advanced_filters,
        }
        if entity_type == "case" and sort:
            all_filters.update({"sort": sort, "direction": "asc" if direction == "asc" else "desc"})
        active_filters = {key: value for key, value in all_filters.items() if value}
        pagination_base = "?" + (urlencode(active_filters) + "&" if active_filters else "") + "page="
        export_query = urlencode({"entity": entity_type, **active_filters})
        sort_urls = {}
        if entity_type == "case":
            for key, _ in meta["list_columns"]:
                next_direction = "desc" if sort == key and direction == "asc" else "asc"
                sort_params = {k: v for k, v in active_filters.items() if k not in ("sort", "direction")}
                sort_params.update({"sort": key, "direction": next_direction})
                sort_urls[key] = "?" + urlencode(sort_params)

        token = auth.get_csrf_token(request)
        response = templates.TemplateResponse(request, "records_list.html", {
            "user": user, "csrf_token": token, "active": meta["active"],
            "entity_type": entity_type, "entity_path": meta["path"], "title": meta["title"],
            "columns": meta["list_columns"], "rows": rows, "total": total,
            "default_visible_columns": CASE_DEFAULT_VISIBLE_COLUMNS if entity_type == "case" else set(),
            "column_count": len(meta["list_columns"]),
            "page": page, "total_pages": total_pages,
            "filters": all_filters, "disease_options": disease_options, "area_options": area_options,
            "status_options": status_options, "advanced_options": advanced_options,
            "advanced_open": records_query.has_advanced_filters(advanced_filters),
            "pagination_base": pagination_base, "export_query": export_query,
            "sort": sort, "direction": direction, "sort_urls": sort_urls,
            "area_label": "Xã/Phường" if entity_type == "case" else "Địa bàn",
            "disease_label": "Chẩn đoán" if entity_type == "case" else "Tên bệnh",
            "can_export": user.has_role(*CAN_EXPORT_ROLES),
            "can_edit_outbreak": user.has_role(*CAN_EDIT_OUTBREAK_ROLES),
            "can_delete_case": entity_type == "case" and user.has_role(*CAN_DELETE_CASE_ROLES),
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
            "can_edit_outbreak": entity_type == "outbreak" and user.has_role(*CAN_EDIT_OUTBREAK_ROLES),
            "can_delete_outbreak": entity_type == "outbreak" and user.has_role(*CAN_DELETE_OUTBREAK_ROLES),
        })
        auth.set_csrf_cookie(response, request, token)
        return response

    return _view


def _outbreak_form_response(
    request: Request, user: auth.CurrentUser, record: dict | None = None, err: str = "", is_edit: bool = False,
):
    token = auth.get_csrf_token(request)
    response = templates.TemplateResponse(request, "outbreak_form.html", {
        "user": user, "csrf_token": token, "active": "o-dich", "record": record or {}, "err": err,
        "fields": [(label, key) for label, key in core.OUTBREAK_FIELDS if key != "source_stt"],
        "is_edit": is_edit,
    })
    auth.set_csrf_cookie(response, request, token)
    return response


@router.get("/cdc/o-dich/them", response_class=HTMLResponse)
def create_outbreak_form(
    request: Request,
    user: auth.CurrentUser = Depends(require_role(*CAN_EDIT_OUTBREAK_ROLES)),
):
    return _outbreak_form_response(request, user)


@router.post("/cdc/o-dich/them", response_class=HTMLResponse)
async def create_outbreak(
    request: Request,
    user: auth.CurrentUser = Depends(require_role(*CAN_EDIT_OUTBREAK_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    form = await request.form()
    if not auth.verify_csrf(request, str(form.get("csrf_token", ""))):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    data = {key: str(form.get(key, "")).strip() for _, key in core.OUTBREAK_FIELDS if key != "source_stt"}
    if not data["disease"] or not data["location"]:
        return _outbreak_form_response(request, user, data, "Tên bệnh và địa điểm là bắt buộc.")
    try:
        record_id = core.save_outbreak(data, db_path=settings.db_path)
    except (TypeError, ValueError) as exc:
        return _outbreak_form_response(request, user, data, str(exc))
    core.log_audit(
        "create_outbreak_web", actor=user.username, detail=f"outbreak_id={record_id}",
        db_path=settings.db_path,
    )
    return RedirectResponse(f"/cdc/o-dich/{record_id}?msg={quote('Đã thêm ổ dịch.')}", status_code=303)


@router.get("/cdc/o-dich/{record_id}/sua", response_class=HTMLResponse)
def edit_outbreak_form(
    record_id: int, request: Request,
    user: auth.CurrentUser = Depends(require_role(*CAN_EDIT_OUTBREAK_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    record = core.get_record("outbreak", record_id, db_path=settings.db_path)
    if not record:
        raise ForbiddenError("Không tìm thấy bản ghi.")
    return _outbreak_form_response(request, user, record, is_edit=True)


@router.post("/cdc/o-dich/{record_id}/sua", response_class=HTMLResponse)
async def edit_outbreak(
    record_id: int, request: Request,
    user: auth.CurrentUser = Depends(require_role(*CAN_EDIT_OUTBREAK_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not core.get_record("outbreak", record_id, db_path=settings.db_path):
        raise ForbiddenError("Không tìm thấy bản ghi.")
    form = await request.form()
    if not auth.verify_csrf(request, str(form.get("csrf_token", ""))):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    data = {key: str(form.get(key, "")).strip() for _, key in core.OUTBREAK_FIELDS if key != "source_stt"}
    data["id"] = record_id
    if not data["disease"] or not data["location"]:
        return _outbreak_form_response(
            request, user, data, "Tên bệnh và địa điểm là bắt buộc.", is_edit=True,
        )
    try:
        core.save_outbreak(data, record_id=record_id, db_path=settings.db_path)
    except (TypeError, ValueError) as exc:
        return _outbreak_form_response(request, user, data, str(exc), is_edit=True)
    core.log_audit(
        "update_outbreak_web", actor=user.username, detail=f"outbreak_id={record_id}",
        db_path=settings.db_path,
    )
    return RedirectResponse(f"/cdc/o-dich/{record_id}?msg={quote('Đã cập nhật ổ dịch.')}", status_code=303)


@router.post("/cdc/o-dich/{record_id}/xoa", response_class=HTMLResponse)
async def delete_outbreak(
    record_id: int, request: Request,
    user: auth.CurrentUser = Depends(require_role(*CAN_DELETE_OUTBREAK_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    form = await request.form()
    if not auth.verify_csrf(request, str(form.get("csrf_token", ""))):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    if not core.get_record("outbreak", record_id, db_path=settings.db_path):
        raise ForbiddenError("Không tìm thấy bản ghi.")
    core.delete_record("outbreak", record_id, db_path=settings.db_path)
    core.log_audit(
        "delete_outbreak_web", actor=user.username, detail=f"outbreak_id={record_id}",
        db_path=settings.db_path,
    )
    return RedirectResponse(f"/cdc/o-dich?msg={quote('Đã xóa ổ dịch.')}", status_code=303)


@router.post("/cdc/ca-benh/{record_id}/xoa", response_class=HTMLResponse)
async def delete_case(
    record_id: int, request: Request,
    user: auth.CurrentUser = Depends(require_role(*CAN_DELETE_CASE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    form = await request.form()
    if not auth.verify_csrf(request, str(form.get("csrf_token", ""))):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    if not core.get_record("case", record_id, db_path=settings.db_path):
        raise ForbiddenError("Không tìm thấy bản ghi.")
    core.delete_record("case", record_id, db_path=settings.db_path)
    core.log_audit(
        "delete_case_web", actor=user.username, detail=f"case_id={record_id}",
        db_path=settings.db_path,
    )
    return RedirectResponse(f"/cdc/ca-benh?msg={quote('Đã xóa ca bệnh.')}", status_code=303)


@router.post("/cdc/ca-benh/xoa-nhieu", response_class=HTMLResponse)
async def delete_cases_batch(
    request: Request, record_ids: list[int] = Form(default=[]), csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_DELETE_CASE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    if not record_ids:
        return RedirectResponse(f"/cdc/ca-benh?err={quote('Chưa chọn ca bệnh nào để xóa.')}", status_code=303)
    deleted = core.delete_records("case", record_ids, db_path=settings.db_path, actor=user.username)
    msg = f"Đã xóa {deleted} ca bệnh."
    return RedirectResponse(f"/cdc/ca-benh?msg={quote(msg)}", status_code=303)


router.add_api_route("/cdc/ca-benh", _list_view("case"), methods=["GET"], response_class=HTMLResponse)
router.add_api_route("/cdc/ca-benh/{record_id}", _detail_view("case"), methods=["GET"], response_class=HTMLResponse)
router.add_api_route("/cdc/o-dich", _list_view("outbreak"), methods=["GET"], response_class=HTMLResponse)
router.add_api_route("/cdc/o-dich/{record_id}", _detail_view("outbreak"), methods=["GET"], response_class=HTMLResponse)
