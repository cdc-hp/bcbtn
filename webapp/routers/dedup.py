"""`/cdc/loc-trung` — Giai đoạn 5 (xem TASKS.md): quét/duyệt/hợp nhất bản ghi trùng qua Web,
thay cho tab "Lọc trùng dữ liệu" của máy trạm PyQt6 (`app.py: DuplicateTab`). Tái dùng nguyên
`core.find_duplicate_groups`/`merge_duplicate_records`/`list_duplicate_actions`/
`restore_duplicate_action` — router chỉ dựng giao diện, không viết lại thuật toán so trùng.

Trang duyệt (`/cdc/loc-trung/xem`) nhận danh sách id bản ghi trực tiếp qua querystring thay vì
`group_id` — tránh phải quét lại toàn bộ (và có thể lệch kết quả nếu dữ liệu vừa đổi) chỉ để tìm
lại đúng nhóm khi người dùng bấm "Duyệt & hợp nhất"."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import core
import duplicate_config
from webapp import auth
from webapp.config import WebAppSettings
from webapp.dependencies import ForbiddenError, get_settings_dep, require_password_current, require_role
from webapp.services.export_files import file_download_response, make_temp_export_path

router = APIRouter()
templates = Jinja2Templates(directory="webapp/templates")

CAN_MERGE_ROLES = (core.CDC_ROLE_SUPER_ADMIN, core.CDC_ROLE_ADMIN, core.CDC_ROLE_DATA_OPERATOR)
CAN_RESTORE_ROLES = (core.CDC_ROLE_SUPER_ADMIN, core.CDC_ROLE_ADMIN)
CAN_CONFIGURE_ROLES = (core.CDC_ROLE_SUPER_ADMIN, core.CDC_ROLE_ADMIN)
CAN_EXPORT_ROLES = (core.CDC_ROLE_SUPER_ADMIN, core.CDC_ROLE_ADMIN, core.CDC_ROLE_DATA_OPERATOR)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _redirect_to_scan(entity_type: str, msg: str = "", err: str = "") -> RedirectResponse:
    url = f"/cdc/loc-trung?entity={entity_type}"
    if msg:
        url += f"&msg={quote(msg)}"
    elif err:
        url += f"&err={quote(err)}"
    return RedirectResponse(url, status_code=303)


def _scan_groups(entity_type: str, min_score: int | None, db_path) -> tuple[list[dict], int]:
    """Trả về (groups, effective_min_score) — effective_min_score chỉ có ý nghĩa với ổ dịch."""
    if entity_type == "case":
        criteria = duplicate_config.load_case_criteria()
        return core.find_duplicate_groups("case", criteria=criteria, db_path=db_path), 0
    rules = duplicate_config.load_rules()
    effective_min_score = min_score if min_score is not None else rules.min_score
    weights = rules.weights_for("outbreak")
    groups = core.find_duplicate_groups(
        "outbreak", min_score=effective_min_score,
        rules={"weights": weights, "definite_score": rules.definite_score}, db_path=db_path,
    )
    return groups, effective_min_score


@router.get("/cdc/loc-trung", response_class=HTMLResponse)
def scan(
    request: Request, entity: str = "case", min_score: int | None = None, msg: str = "", err: str = "",
    user: auth.CurrentUser = Depends(require_password_current),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    entity_type = entity if entity in ("case", "outbreak") else "case"
    groups, effective_min_score = _scan_groups(entity_type, min_score, settings.db_path)
    rows = []
    for group in groups:
        row = {k: v for k, v in group.items() if k != "records"}
        row["case_codes_text"] = ", ".join(code for code in group.get("case_codes") or [] if code)
        row["review_url"] = "/cdc/loc-trung/xem?entity=%s&ids=%s" % (
            entity_type, ",".join(str(i) for i in group["record_ids"]),
        )
        rows.append(row)
    total_records = sum(int(g["record_count"]) for g in groups)
    case_criteria = duplicate_config.load_case_criteria()
    criteria_text = ", ".join(
        duplicate_config.CASE_CRITERIA_LABELS.get(c, c) for c in case_criteria.enabled
    )

    token = auth.get_csrf_token(request)
    response = templates.TemplateResponse(request, "dedup.html", {
        "user": user, "csrf_token": token, "active": "loc-trung",
        "entity_type": entity_type, "rows": rows, "total_groups": len(groups), "total_records": total_records,
        "min_score": effective_min_score, "criteria_text": criteria_text,
        "can_merge": user.has_role(*CAN_MERGE_ROLES), "can_export": user.has_role(*CAN_EXPORT_ROLES),
        "can_configure": user.has_role(*CAN_CONFIGURE_ROLES), "msg": msg, "err": err,
    })
    auth.set_csrf_cookie(response, request, token)
    return response


@router.get("/cdc/loc-trung/xuat")
def export_scan(
    entity: str = "case", min_score: int | None = None,
    user: auth.CurrentUser = Depends(require_role(*CAN_EXPORT_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    entity_type = entity if entity in ("case", "outbreak") else "case"
    groups, _ = _scan_groups(entity_type, min_score, settings.db_path)
    if entity_type == "case":
        columns = ["Nhóm", "Mức", "Mã ca bệnh liên quan", "Số bản ghi", "Danh sách ID", "Tóm tắt", "Tiêu chí khớp"]
        rows = [[
            g["group_id"], g["confidence"], ", ".join(c for c in g.get("case_codes") or [] if c),
            g["record_count"], ", ".join(map(str, g["record_ids"])), g["summary"], g["reasons"],
        ] for g in groups]
    else:
        columns = ["Nhóm", "Mức", "Điểm", "Số bản ghi", "Danh sách ID", "Tóm tắt", "Lý do"]
        rows = [[
            g["group_id"], g["confidence"], g["score"], g["record_count"],
            ", ".join(map(str, g["record_ids"])), g["summary"], g["reasons"],
        ] for g in groups]
    tmp_path = make_temp_export_path(".xlsx")
    core.export_rows(tmp_path, columns, rows)
    return file_download_response(tmp_path, f"ket_qua_loc_trung_{entity_type}_{_timestamp()}.xlsx")


@router.get("/cdc/loc-trung/xem", response_class=HTMLResponse)
def review(
    request: Request, entity: str, ids: str,
    user: auth.CurrentUser = Depends(require_password_current),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    entity_type = entity if entity in ("case", "outbreak") else "case"
    id_list: list[int] = []
    for part in ids.split(","):
        part = part.strip()
        if part.isdigit() and int(part) not in id_list:
            id_list.append(int(part))
    records = core.get_records_by_ids(entity_type, id_list[:50], db_path=settings.db_path)
    if len(records) < 2:
        return _redirect_to_scan(entity_type, err="Nhóm này không còn đủ bản ghi để hợp nhất (có thể đã được xử lý).")

    fields = core.CASE_MERGE_FIELDS if entity_type == "case" else core.OUTBREAK_MERGE_FIELDS
    labels = core.CASE_LABELS if entity_type == "case" else core.OUTBREAK_LABELS
    default_record = records[0]
    merge_rows = []
    for field in fields:
        values: list[str] = []
        for record in records:
            text = "" if record.get(field) is None else str(record.get(field))
            if text not in values:
                values.append(text)
        non_empty = {v for v in values if v}
        default_value = "" if default_record.get(field) is None else str(default_record.get(field))
        merge_rows.append({
            "field": field, "label": labels.get(field, field), "options": values,
            "default": default_value, "differs": len(non_empty) > 1,
        })
    compare_columns = [("id", "ID")] + [(f, labels.get(f, f)) for f in fields]

    token = auth.get_csrf_token(request)
    response = templates.TemplateResponse(request, "dedup_review.html", {
        "user": user, "csrf_token": token, "active": "loc-trung",
        "entity_type": entity_type, "records": records, "ids": id_list,
        "merge_rows": merge_rows, "compare_columns": compare_columns,
        "can_merge": user.has_role(*CAN_MERGE_ROLES),
    })
    auth.set_csrf_cookie(response, request, token)
    return response


@router.post("/cdc/loc-trung/hop-nhat", response_class=HTMLResponse)
async def merge_group(
    request: Request,
    user: auth.CurrentUser = Depends(require_role(*CAN_MERGE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    form = await request.form()
    if not auth.verify_csrf(request, str(form.get("csrf_token", ""))):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF). Tải lại trang và thử lại.")
    entity_type = str(form.get("entity", ""))
    if entity_type not in ("case", "outbreak"):
        raise ForbiddenError("Loại bản ghi không hợp lệ.")
    try:
        ids = [int(v) for v in form.getlist("ids")]
        keep_id = int(str(form.get("keep", "")))
    except ValueError:
        return _redirect_to_scan(entity_type, err="Dữ liệu gửi lên không hợp lệ.")
    remove_ids = [i for i in ids if i != keep_id]
    fields = core.CASE_MERGE_FIELDS if entity_type == "case" else core.OUTBREAK_MERGE_FIELDS
    merged_values = {field: str(form.get(f"field__{field}", "")) for field in fields}
    try:
        result = core.merge_duplicate_records(
            entity_type, keep_id, remove_ids, merged_values, db_path=settings.db_path, actor=user.username,
        )
    except ValueError as exc:
        return _redirect_to_scan(entity_type, err=str(exc))
    return _redirect_to_scan(
        entity_type, msg=f"Đã giữ ID {result['kept_id']}, đưa {result['removed_count']} bản ghi vào Thùng rác."
    )


@router.get("/cdc/loc-trung/lich-su", response_class=HTMLResponse)
def history(
    request: Request, msg: str = "", err: str = "",
    user: auth.CurrentUser = Depends(require_password_current),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    rows = core.list_duplicate_actions(db_path=settings.db_path)
    for item in rows:
        item["entity_label"] = "Ca bệnh" if item.get("entity_type") == "case" else "Ổ dịch"
        item["action_label"] = "Hợp nhất" if item.get("action_type") == "merge" else "Loại trùng"

    token = auth.get_csrf_token(request)
    response = templates.TemplateResponse(request, "dedup_history.html", {
        "user": user, "csrf_token": token, "active": "loc-trung", "rows": rows,
        "can_restore": user.has_role(*CAN_RESTORE_ROLES), "msg": msg, "err": err,
    })
    auth.set_csrf_cookie(response, request, token)
    return response


@router.post("/cdc/loc-trung/khoi-phuc/{action_id}", response_class=HTMLResponse)
async def restore(
    action_id: int, request: Request, csrf_token: str = Form(""),
    user: auth.CurrentUser = Depends(require_role(*CAN_RESTORE_ROLES)),
    settings: WebAppSettings = Depends(get_settings_dep),
):
    if not auth.verify_csrf(request, csrf_token):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    try:
        result = core.restore_duplicate_action(action_id, db_path=settings.db_path, actor=user.username)
    except ValueError as exc:
        return RedirectResponse(f"/cdc/loc-trung/lich-su?err={quote(str(exc))}", status_code=303)
    restored_msg = f"Đã khôi phục {result['restored_count']} bản ghi."
    return RedirectResponse(f"/cdc/loc-trung/lich-su?msg={quote(restored_msg)}", status_code=303)


@router.get("/cdc/loc-trung/tieu-chi", response_class=HTMLResponse)
def criteria_form(
    request: Request, entity: str = "case", msg: str = "",
    user: auth.CurrentUser = Depends(require_role(*CAN_CONFIGURE_ROLES)),
):
    entity_type = entity if entity in ("case", "outbreak") else "case"
    case_criteria = duplicate_config.load_case_criteria()
    rules = duplicate_config.load_rules()

    token = auth.get_csrf_token(request)
    response = templates.TemplateResponse(request, "dedup_criteria.html", {
        "user": user, "csrf_token": token, "active": "loc-trung", "entity_type": entity_type,
        "criteria_defs": duplicate_config.CASE_CRITERIA_DEFS, "case_criteria": case_criteria,
        "rules": rules, "outbreak_weight_defs": duplicate_config.DEFAULT_OUTBREAK_WEIGHTS, "msg": msg,
    })
    auth.set_csrf_cookie(response, request, token)
    return response


@router.post("/cdc/loc-trung/tieu-chi", response_class=HTMLResponse)
async def save_criteria(
    request: Request,
    user: auth.CurrentUser = Depends(require_role(*CAN_CONFIGURE_ROLES)),
):
    form = await request.form()
    if not auth.verify_csrf(request, str(form.get("csrf_token", ""))):
        raise ForbiddenError("Phiên làm việc đã hết hạn hoặc yêu cầu không hợp lệ (CSRF).")
    entity_type = str(form.get("entity", "case"))
    if entity_type == "case":
        criteria = duplicate_config.CaseDuplicateCriteria(
            enabled=list(form.getlist("enabled")),
            name_similarity_percent=int(str(form.get("name_similarity_percent", "92")) or 92),
            onset_max_days=int(str(form.get("onset_max_days", "3")) or 3),
        )
        duplicate_config.save_case_criteria(criteria)
    else:
        weights = {
            key: int(str(form.get(f"weight__{key}", default)) or default)
            for key, default in duplicate_config.DEFAULT_OUTBREAK_WEIGHTS.items()
        }
        rules = duplicate_config.DuplicateRules(
            min_score=int(str(form.get("min_score", "65")) or 65),
            definite_score=int(str(form.get("definite_score", "85")) or 85),
            outbreak_weights=weights,
        )
        duplicate_config.save_rules(rules)
    return RedirectResponse(
        f"/cdc/loc-trung/tieu-chi?entity={entity_type}&msg={quote('Đã lưu cấu hình.')}", status_code=303,
    )
