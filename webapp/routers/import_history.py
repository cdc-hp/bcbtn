"""`/cdc/lich-su-nhap` — lịch sử các lần nhập Excel (bảng `import_batches`), cho phép xóa nguyên
một lần nhập (mọi ca bệnh/ổ dịch sinh ra từ đúng file + thời điểm nhập đó) khi CDC phát hiện nhập
nhầm file — xem `core.delete_import_batch`."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import core
from webapp import TEMPLATES_DIR, auth
from webapp.config import WebAppSettings
from webapp.dependencies import ForbiddenError, get_settings_dep, require_role
from webapp.services.export_files import file_download_response, make_temp_export_path
from webapp.services.pagination import paginate

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)

CAN_VIEW_ROLES = (core.CDC_ROLE_SUPER_ADMIN, core.CDC_ROLE_ADMIN, core.CDC_ROLE_DATA_OPERATOR)
CAN_DELETE_ROLES = (core.CDC_ROLE_SUPER_ADMIN, core.CDC_ROLE_ADMIN)
ENTITY_LABELS = {"case": "Ca bệnh", "outbreak": "Ổ dịch"}

# Tiêu đề bảng nào bấm sắp xếp được — khớp đúng whitelist core.BATCH_SORT_COLUMNS.
SORTABLE_COLUMNS = {
    "imported_at": "Thời điểm nhập", "commune": "Xã", "week": "Tuần", "file_name": "File",
    "entity_type": "Loại", "rows_read": "Đã đọc", "inserted": "Đã thêm", "duplicates": "Trùng",
    "issue_count": "Cảnh báo",
}


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _sort_links(base_params: dict, current_sort: str, current_dir: str) -> dict[str, dict[str, str]]:
    """Tính sẵn URL + chiều mũi tên cho từng cột sắp xếp được — bấm lần đầu sắp xếp tăng dần,
    bấm lại đúng cột đó đảo chiều, bấm cột khác luôn bắt đầu lại từ tăng dần (khớp mẫu
    routers/queue.py::_sort_links)."""
    links: dict[str, dict[str, str]] = {}
    for column in SORTABLE_COLUMNS:
        next_dir = "desc" if current_sort == column and current_dir == "asc" else "asc"
        params = {**base_params, "sort": column, "dir": next_dir}
        params = {k: v for k, v in params.items() if v}
        links[column] = {
            "url": "/cdc/lich-su-nhap?" + urlencode(params),
            "active": current_sort == column,
            "dir": current_dir if current_sort == column else "",
        }
    return links


@router.get("/cdc/lich-su-nhap", response_class=HTMLResponse)
def list_batches(
    request: Request, commune: str = "", week: str = "", sort: str = "", dir: str = "asc",
    msg: str = "", err: str = "", page: int = 1,
    user: auth.CurrentUser = Depends(require_role(*CAN_VIEW_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    sort = sort if sort in SORTABLE_COLUMNS else ""
    dir = "desc" if dir == "desc" else "asc"
    rows = core.list_import_batches(
        db_path=settings.db_path, limit=2000, commune=commune, week=week, sort=sort, direction=dir,
    )
    for row in rows:
        row["entity_label"] = ENTITY_LABELS.get(row["entity_type"], row["entity_type"])
        row["imported_at"] = core.format_timestamp_for_display(row.get("imported_at"))
    page_rows, page_info = paginate(rows, page)
    base_params = {"commune": commune, "week": week}
    # pagination_base GIỮ NGUYÊN sort/dir đang chọn (khớp mẫu queue.py) — đổi trang không làm
    # mất cách sắp xếp hiện tại; ngược lại _sort_links KHÔNG mang `page` — bấm đổi sort tự về trang 1.
    pagination_params = {k: v for k, v in {**base_params, "sort": sort, "dir": dir}.items() if v}
    pagination_base = "/cdc/lich-su-nhap?" + (urlencode(pagination_params) + "&" if pagination_params else "") + "page="
    export_query = urlencode(pagination_params)
    token = auth.get_csrf_token(request)
    response = templates.TemplateResponse(request, "import_history.html", {
        "user": user, "csrf_token": token, "active": "lich-su-nhap",
        "rows": page_rows, "total": page_info["total"],
        "filters": {"commune": commune, "week": week, "sort": sort, "dir": dir},
        "official_communes": sorted(core.OFFICIAL_COMMUNES),
        "sort_links": _sort_links(base_params, sort, dir),
        "export_query": export_query,
        "page": page_info["page"], "total_pages": page_info["total_pages"],
        "pagination_base": pagination_base,
        "can_delete": user.has_role(*CAN_DELETE_ROLES), "msg": msg, "err": err,
    })
    auth.set_csrf_cookie(response, request, token)
    return response


@router.get("/cdc/lich-su-nhap/xuat")
def export_batches(
    commune: str = "", week: str = "", sort: str = "", dir: str = "asc",
    user: auth.CurrentUser = Depends(require_role(*CAN_VIEW_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    sort = sort if sort in SORTABLE_COLUMNS else ""
    dir = "desc" if dir == "desc" else "asc"
    rows = core.list_import_batches(
        db_path=settings.db_path, limit=2000, commune=commune, week=week, sort=sort, direction=dir,
    )
    columns = ["Thời điểm nhập", "Xã", "Tuần", "File", "Loại", "Đã đọc", "Đã thêm", "Trùng", "Cảnh báo"]
    export_data = [[
        core.format_timestamp_for_display(row["imported_at"]), row.get("commune") or "—", row.get("week") or "—",
        row["file_name"], ENTITY_LABELS.get(row["entity_type"], row["entity_type"]),
        row["rows_read"], row["inserted"], row["duplicates"], row["issue_count"],
    ] for row in rows]
    tmp_path = make_temp_export_path(".xlsx")
    core.export_rows(tmp_path, columns, export_data)
    return file_download_response(tmp_path, f"lich_su_nhap_{_timestamp()}.xlsx")


@router.post("/cdc/lich-su-nhap/{batch_id}/xoa", response_class=HTMLResponse)
async def delete_batch(
    batch_id: int, request: Request, csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_DELETE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    try:
        result = core.delete_import_batch(batch_id, db_path=settings.db_path, actor=user.username)
    except ValueError as exc:
        return RedirectResponse(f"/cdc/lich-su-nhap?err={quote(str(exc))}", status_code=303)
    label = ENTITY_LABELS.get(result["entity_type"], result["entity_type"])
    msg = f"Đã xóa {result['deleted_count']} {label.lower()} từ file {result['file_name']}."
    return RedirectResponse(f"/cdc/lich-su-nhap?msg={quote(msg)}", status_code=303)


@router.post("/cdc/lich-su-nhap/xoa-nhieu", response_class=HTMLResponse)
async def delete_batches(
    request: Request, batch_ids: list[int] = Form(default=[]), csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_DELETE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    if not batch_ids:
        return RedirectResponse("/cdc/lich-su-nhap?err=" + quote("Chưa chọn lần nhập nào để xóa."), status_code=303)
    ok_count = 0
    deleted_records = 0
    errors: list[str] = []
    for bid in batch_ids:
        try:
            result = core.delete_import_batch(bid, db_path=settings.db_path, actor=user.username)
            ok_count += 1
            deleted_records += result["deleted_count"]
        except ValueError as exc:
            errors.append(f"#{bid}: {exc}")
    if errors:
        err = f"Đã xóa {ok_count}/{len(batch_ids)} lần nhập ({deleted_records} bản ghi). Lỗi: " + "; ".join(errors)
        return RedirectResponse(f"/cdc/lich-su-nhap?err={quote(err)}", status_code=303)
    msg = f"Đã xóa {ok_count} lần nhập ({deleted_records} bản ghi)."
    return RedirectResponse(f"/cdc/lich-su-nhap?msg={quote(msg)}", status_code=303)
