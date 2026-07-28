from __future__ import annotations

import tempfile
from pathlib import Path

from openpyxl import Workbook

import backup_manager
import core


def make_excel(path: Path, fields, rows, sheet="Disease Cases"):
    wb = Workbook(); ws = wb.active; ws.title = sheet
    ws.append([label for label, _ in fields])
    for values in rows:
        ws.append([values.get(key, "") for _, key in fields])
    wb.save(path)


def configure_temp_backup(root: Path):
    core.BACKUP_DIR = root / "backups"
    backup_manager.LOCAL_BACKUP_DIR = root / "backups"
    backup_manager.CONFIG_PATH = root / "backup_policy.json"


def test_merge_to_trash_and_restore():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp); configure_temp_backup(root); db = root / "main.db"
        file = root / "cases.xlsx"
        base = {
            "full_name": "Nguyễn Văn A", "birth_date_raw": "01/01/1990", "gender": "Nam",
            "phone": "0901234567", "commune": "Phường Gia Viên",
            "main_diagnosis": "Sốt xuất huyết Dengue", "onset_date": "10/07/2026",
            "report_datetime": "11/07/2026 08:00", "reporting_unit": "Trạm Y tế",
        }
        make_excel(file, core.CASE_FIELDS, [dict(base, case_code="CA-1"), dict(base, case_code="CA-2", current_address="Gia Viên")])
        assert core.import_excel(file, db).inserted == 2
        group = core.find_duplicate_groups(
            "case", db_path=db, criteria={"enabled": ["phone", "full_name", "birth_date_raw"]}
        )[0]
        keep, remove = group["record_ids"][0], group["record_ids"][1:]
        result = core.merge_duplicate_records("case", keep, remove, {"phone": "0911111111", "full_name": "Nguyễn Văn A"}, db)
        assert result["removed_count"] == 1
        assert Path(result["backup_file"]).exists()
        kept = core.get_record("case", keep, db)
        assert kept["phone"] == "0911111111"
        assert core.dashboard_stats(db)["case_records"] == 1
        actions = core.list_duplicate_actions(db_path=db)
        assert actions[0]["pending_count"] == 1
        restored = core.restore_duplicate_action(result["action_id"], db)
        assert restored["restored_count"] == 1
        assert core.dashboard_stats(db)["case_records"] == 2
        assert core.list_duplicate_actions(db_path=db)[0]["pending_count"] == 0


def test_backup_verify_and_restore_database():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp); configure_temp_backup(root); db = root / "main.db"
        file = root / "outbreaks.xlsx"
        rows = [{"disease": "Sốt xuất huyết Dengue", "location": "Gia Viên", "first_onset_date": "10/07/2026", "case_count": 2, "report_datetime": "11/07/2026"}]
        make_excel(file, core.OUTBREAK_FIELDS, rows, "Danh sách ổ dịch")
        assert core.import_excel(file, db).inserted == 1
        policy = backup_manager.BackupPolicy(destination=str(root / "archive"), verify_after_backup=True)
        backup_manager.save_policy(policy)
        backup = backup_manager.create_backup(db, kind="manual", policy=policy)
        assert backup_manager.verify_backup(backup)["ok"]
        core.save_outbreak({"disease": "Sởi", "location": "Lê Chân", "first_onset_date": "12/07/2026"}, db_path=db)
        assert core.dashboard_stats(db)["outbreak_records"] == 2
        result = backup_manager.restore_backup(backup, db, policy)
        assert Path(result["safety_backup"]).exists()
        assert core.dashboard_stats(db)["outbreak_records"] == 1


def test_all_new_sources_compile():
    root = Path(__file__).parents[1]
    for name in ("core.py", "deployment_config.py", "backup_manager.py", "duplicate_config.py", "service_windows.py"):
        compile((root / name).read_text(encoding="utf-8"), name, "exec")
