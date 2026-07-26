"""Dữ liệu tổng quan phục vụ đúng các khối có trong prototype Web App."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import core


def _connect(db_path: Path | str) -> sqlite3.Connection:
    core.init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def disease_options(db_path: Path | str = core.DB_PATH) -> list[str]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """SELECT disease FROM (
                   SELECT main_diagnosis AS disease FROM cases
                   UNION SELECT disease FROM outbreaks
               ) WHERE COALESCE(disease, '') <> '' ORDER BY disease"""
        ).fetchall()
    return [str(row[0]) for row in rows]


def dashboard_metrics(disease: str = "", db_path: Path | str = core.DB_PATH) -> dict[str, Any]:
    case_where = " WHERE main_diagnosis = ?" if disease else ""
    outbreak_where = " WHERE disease = ?" if disease else ""
    params = [disease] if disease else []
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    week_start = monday.isoformat()
    week_end = (monday + timedelta(days=7)).isoformat()

    with _connect(db_path) as conn:
        case_records = int(conn.execute(f"SELECT COUNT(*) FROM cases{case_where}", params).fetchone()[0])
        outbreak_records = int(conn.execute(f"SELECT COUNT(*) FROM outbreaks{outbreak_where}", params).fetchone()[0])
        active_sql = "SELECT COUNT(*) FROM outbreaks WHERE status LIKE '%Đang hoạt động%'"
        active_params: list[Any] = []
        if disease:
            active_sql += " AND disease = ?"
            active_params.append(disease)
        active_outbreaks = int(conn.execute(active_sql, active_params).fetchone()[0])

        weekly_sql = "SELECT COUNT(*) FROM cases WHERE onset_date >= ? AND onset_date < ?"
        weekly_params: list[Any] = [week_start, week_end]
        if disease:
            weekly_sql += " AND main_diagnosis = ?"
            weekly_params.append(disease)
        current_week_cases = int(conn.execute(weekly_sql, weekly_params).fetchone()[0])

        issue_sql = """SELECT COUNT(*) FROM data_quality_issues i
                       WHERE i.severity IN ('error','warning')"""
        issue_params: list[Any] = []
        if disease:
            issue_sql += """ AND (
                (i.entity_type='case' AND EXISTS (
                    SELECT 1 FROM cases c WHERE c.id=i.entity_id AND c.main_diagnosis=?
                )) OR
                (i.entity_type='outbreak' AND EXISTS (
                    SELECT 1 FROM outbreaks o WHERE o.id=i.entity_id AND o.disease=?
                ))
            )"""
            issue_params.extend([disease, disease])
        quality_issues = int(conn.execute(issue_sql, issue_params).fetchone()[0])

        weekly_trend: list[dict[str, Any]] = []
        for offset in range(7, -1, -1):
            start = monday - timedelta(weeks=offset)
            end = start + timedelta(days=7)
            sql = "SELECT COUNT(*) FROM cases WHERE onset_date >= ? AND onset_date < ?"
            values: list[Any] = [start.isoformat(), end.isoformat()]
            if disease:
                sql += " AND main_diagnosis = ?"
                values.append(disease)
            count = int(conn.execute(sql, values).fetchone()[0])
            weekly_trend.append({"label": f"T{start.isocalendar().week}", "count": count})

    max_count = max((item["count"] for item in weekly_trend), default=0)
    for item in weekly_trend:
        item["percent"] = max(6, round(item["count"] * 100 / max_count)) if max_count else 6
    return {
        "case_records": case_records,
        "outbreak_records": outbreak_records,
        "active_outbreaks": active_outbreaks,
        "current_week_cases": current_week_cases,
        "quality_issues": quality_issues,
        "weekly_trend": weekly_trend,
        "updated_at": datetime.now().strftime("%H:%M"),
    }
