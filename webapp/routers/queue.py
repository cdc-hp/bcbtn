"""`/cdc/hang-doi` — Section 6 của nhiệm vụ Web App: lọc theo xã/tuần/trạng thái/nguồn, xem,
tải file gốc, nhập (một/nhiều), xem lỗi, nhập lại, xoá theo quyền. Chống 2 người cùng nhập 1
file đã có sẵn ở `core.import_queue_item` (UPDATE nguyên tử) — router chỉ cần bắt ValueError."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import core
from webapp import TEMPLATES_DIR, auth
from webapp.config import WebAppSettings
from webapp.dependencies import ForbiddenError, get_settings_dep, require_password_current, require_role
from webapp.services.export_files import file_download_response, make_temp_export_path
from webapp.services.http import client_ip
from webapp.services.pagination import paginate

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)

STATUS_LABELS = {"cho_nhap": "Chờ nhập", "dang_nhap": "Đang nhập...", "da_nhap": "Đã nhập", "loi": "Lỗi"}
SOURCE_LABELS = {"server_chinh": "Trực tiếp", "server_phu": "Qua máy chủ phụ"}

CAN_IMPORT_ROLES = (core.CDC_ROLE_SUPER_ADMIN, core.CDC_ROLE_ADMIN, core.CDC_ROLE_DATA_OPERATOR)
CAN_DELETE_ROLES = (core.CDC_ROLE_SUPER_ADMIN, core.CDC_ROLE_ADMIN)

# Tiêu đề bảng nào bấm sắp xếp được — khớp đúng whitelist core.QUEUE_SORT_COLUMNS.
SORTABLE_COLUMNS = {
    "commune": "Xã", "week": "Tuần", "file_name": "File", "source": "Nguồn",
    "status": "Trạng thái", "submitted_by": "Người nộp", "received_at": "Nhận lúc",
}


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _sort_links(base_params: dict, current_sort: str, current_dir: str) -> dict[str, dict[str, str]]:
    """Tính sẵn URL + chiều mũi tên cho từng cột sắp xếp được — bấm lần đầu sắp xếp tăng dần,
    bấm lại đúng cột đó đảo chiều, bấm cột khác luôn bắt đầu lại từ tăng dần."""
    links: dict[str, dict[str, str]] = {}
    for column in SORTABLE_COLUMNS:
        next_dir = "desc" if current_sort == column and current_dir == "asc" else "asc"
        params = {**base_params, "sort": column, "dir": next_dir}
        params = {k: v for k, v in params.items() if v}
        links[column] = {
            "url": "/cdc/hang-doi?" + urlencode(params),
            "active": current_sort == column,
            "dir": current_dir if current_sort == column else "",
        }
    return links


def _redirect_to_list(request: Request, msg: str = "", err: str = "") -> RedirectResponse:
    qs = request.url.query
    base = "/cdc/hang-doi" + (f"?{qs}" if qs else "")
    sep = "&" if "?" in base else "?"
    if msg:
        base += f"{sep}msg={quote(msg)}"
    elif err:
        base += f"{sep}err={quote(err)}"
    return RedirectResponse(base, status_code=303)


@router.get("/cdc/hang-doi", response_class=HTMLResponse)
def queue_list(
    request: Request,
    commune: str = "", week: str = "", status: str = "", source: str = "",
    sort: str = "", dir: str = "asc", page: int = 1,
    msg: str = "", err: str = "",
    user: auth.CurrentUser = Depends(require_password_current),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    sort = sort if sort in SORTABLE_COLUMNS else ""
    dir = "desc" if dir == "desc" else "asc"
    items = core.list_import_queue(
        status=status, commune=commune, week=week, source=source,
        sort=sort, direction=dir, db_path=settings.db_path,
    )
    # Cảnh báo xã nộp từ 2 lần trở lên trong CÙNG một tuần (đếm trên toàn bộ kết quả đang khớp
    # bộ lọc, không chỉ trang hiện tại) — có thể là nộp trùng nhầm hoặc nộp lại bản đã sửa, CDC
    # cần chú ý xem qua trước khi nhập.
    week_counts: dict[tuple[str, str], int] = {}
    for item in items:
        key = (item["commune"], item["week"])
        week_counts[key] = week_counts.get(key, 0) + 1
    rows = []
    for item in items:
        row = dict(item)
        row["status_label"] = STATUS_LABELS.get(item["status"], item["status"])
        row["source_label"] = SOURCE_LABELS.get(item["source"], item["source"])
        row["received_at"] = core.format_timestamp_for_display(row.get("received_at"))
        row["week_submission_count"] = week_counts[(item["commune"], item["week"])]
        rows.append(row)
    page_rows, page_info = paginate(rows, page)
    token = auth.get_csrf_token(request)
    base_params = {"commune": commune, "week": week, "status": status, "source": source}
    # pagination_base GIỮ NGUYÊN sort/dir đang chọn (khớp mẫu records.py) — đổi trang không làm
    # mất cách sắp xếp hiện tại; ngược lại _sort_links KHÔNG mang `page` — bấm đổi sort tự về
    # trang 1 (đúng hành vi records_list.html đang dùng).
    pagination_params = {k: v for k, v in {**base_params, "sort": sort, "dir": dir}.items() if v}
    pagination_base = "/cdc/hang-doi?" + (urlencode(pagination_params) + "&" if pagination_params else "") + "page="
    export_query = urlencode(pagination_params)
    response = templates.TemplateResponse(request, "queue.html", {
        "user": user, "csrf_token": token, "rows": page_rows, "active": "hang-doi",
        "filters": {"commune": commune, "week": week, "status": status, "source": source, "sort": sort, "dir": dir},
        "status_options": STATUS_LABELS, "source_options": SOURCE_LABELS,
        "official_communes": sorted(core.OFFICIAL_COMMUNES),
        "sort_links": _sort_links(base_params, sort, dir),
        "page": page_info["page"], "total_pages": page_info["total_pages"], "total": page_info["total"],
        "pagination_base": pagination_base, "export_query": export_query,
        "can_import": user.has_role(*CAN_IMPORT_ROLES), "can_delete": user.has_role(*CAN_DELETE_ROLES),
        "queue_pending": len(core.list_import_queue(status="cho_nhap", limit=2000, db_path=settings.db_path)),
        "queue_error": len(core.list_import_queue(status="loi", limit=2000, db_path=settings.db_path)),
        "msg": msg, "err": err,
    })
    auth.set_csrf_cookie(response, request, token)
    return response


@router.get("/cdc/hang-doi/xuat")
def export_queue(
    commune: str = "", week: str = "", status: str = "", source: str = "",
    sort: str = "", dir: str = "asc",
    user: auth.CurrentUser = Depends(require_password_current),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    sort = sort if sort in SORTABLE_COLUMNS else ""
    dir = "desc" if dir == "desc" else "asc"
    items = core.list_import_queue(
        status=status, commune=commune, week=week, source=source,
        sort=sort, direction=dir, limit=2000, db_path=settings.db_path,
    )
    week_counts: dict[tuple[str, str], int] = {}
    for item in items:
        key = (item["commune"], item["week"])
        week_counts[key] = week_counts.get(key, 0) + 1
    columns = ["Xã", "Tuần", "File", "Nguồn", "Trạng thái", "Người nộp", "Nhận lúc", "Cảnh báo"]
    export_data = [[
        item["commune"], item["week"], item["file_name"], SOURCE_LABELS.get(item["source"], item["source"]),
        STATUS_LABELS.get(item["status"], item["status"]), item.get("submitted_by") or "",
        core.format_timestamp_for_display(item.get("received_at")),
        "Nộp từ 2 lần trở lên trong tuần" if week_counts[(item["commune"], item["week"])] >= 2 else "",
    ] for item in items]
    tmp_path = make_temp_export_path(".xlsx")
    core.export_rows(tmp_path, columns, export_data)
    return file_download_response(tmp_path, f"hang_doi_{_timestamp()}.xlsx")


@router.get("/cdc/hang-doi/{queue_id}/download")
def download_file(
    queue_id: int,
    user: auth.CurrentUser = Depends(require_password_current),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    items = core.list_import_queue(limit=2000, db_path=settings.db_path)
    item = next((i for i in items if i["id"] == queue_id), None)
    if not item:
        raise ForbiddenError("Không tìm thấy mục trong hàng đợi.")
    from pathlib import Path
    file_path = Path(item["file_path"])
    if not file_path.exists():
        raise ForbiddenError("File không còn tồn tại trên máy chủ.")
    return FileResponse(file_path, filename=item["file_name"])


@router.post("/cdc/hang-doi/{queue_id}/import", response_class=HTMLResponse)
async def import_one(
    queue_id: int, request: Request, csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_IMPORT_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    try:
        result = core.import_queue_item(queue_id, db_path=settings.db_path, actor=user.username)
    except ValueError as exc:
        return _redirect_to_list(request, err=str(exc))
    return _redirect_to_list(
        request, msg=f"Đã nhập {result['file_name']}: thêm {result['inserted']}, trùng {result['duplicates']}, bỏ qua {result['skipped']}."
    )


@router.post("/cdc/hang-doi/import-batch", response_class=HTMLResponse)
async def import_batch(
    request: Request, queue_ids: list[int] = Form(default=[]), csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_IMPORT_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    if not queue_ids:
        return _redirect_to_list(request, err="Chưa chọn mục nào để nhập.")
    ok_count = 0
    errors: list[str] = []
    for qid in queue_ids:
        try:
            core.import_queue_item(qid, db_path=settings.db_path, actor=user.username)
            ok_count += 1
        except ValueError as exc:
            errors.append(f"#{qid}: {exc}")
    if errors:
        return _redirect_to_list(request, err=f"Đã nhập {ok_count}/{len(queue_ids)} mục. Lỗi: " + "; ".join(errors))
    return _redirect_to_list(request, msg=f"Đã nhập thành công {ok_count} mục.")


@router.post("/cdc/hang-doi/{queue_id}/delete", response_class=HTMLResponse)
async def delete_one(
    queue_id: int, request: Request, csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_DELETE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    try:
        core.delete_queue_item(queue_id, db_path=settings.db_path, actor=user.username)
    except ValueError as exc:
        return _redirect_to_list(request, err=str(exc))
    return _redirect_to_list(request, msg="Đã xoá mục khỏi hàng đợi.")
