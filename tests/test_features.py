from __future__ import annotations

import tempfile
from pathlib import Path

from openpyxl import Workbook

import core
import deployment_config


def make_excel(path: Path, fields, rows, sheet='Disease Cases'):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append([label for label, _ in fields])
    for values in rows:
        ws.append([values.get(key, '') for _, key in fields])
    wb.save(path)


def test_case_duplicate_detection_and_removal():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = root / 'test.db'
        core.BACKUP_DIR = root / 'backups'
        file = root / 'cases.xlsx'
        base = {
            'full_name': 'Nguyễn Văn A', 'birth_date_raw': '01/01/1990', 'gender': 'Nam',
            'phone': '0901234567', 'commune': 'Phường Gia Viên',
            'main_diagnosis': 'Sốt xuất huyết Dengue', 'onset_date': '10/07/2026',
            'report_datetime': '11/07/2026 08:00', 'reporting_unit': 'Trạm Y tế',
        }
        rows = [dict(base, case_code='CA-001'), dict(base, case_code='CA-001-B', current_address='Gia Viên, Hải Phòng')]
        make_excel(file, core.CASE_FIELDS, rows)
        summary = core.import_excel(file, db)
        assert summary.inserted == 2
        groups = core.find_duplicate_groups('case', db_path=db, criteria={"enabled": ["phone", "full_name", "birth_date_raw"]})
        assert len(groups) == 1
        assert groups[0]['confidence'] == 'Nghi trùng'
        assert 'Điện thoại' in groups[0]['matched_criteria']
        ids = groups[0]['record_ids']
        result = core.remove_duplicate_records('case', ids[0], ids[1:], db_path=db)
        assert result['removed_count'] == 1
        assert Path(result['backup_file']).exists()
        assert core.dashboard_stats(db)['case_records'] == 1


def test_dismiss_duplicate_pairs_hides_case_group():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = root / 'test.db'
        core.BACKUP_DIR = root / 'backups'
        file = root / 'cases.xlsx'
        base = {
            'full_name': 'Nguyễn Văn A', 'birth_date_raw': '01/01/1990', 'gender': 'Nam',
            'phone': '0901234567', 'commune': 'Phường Gia Viên',
            'main_diagnosis': 'Sốt xuất huyết Dengue', 'onset_date': '10/07/2026',
            'report_datetime': '11/07/2026 08:00', 'reporting_unit': 'Trạm Y tế',
        }
        rows = [dict(base, case_code='CA-001'), dict(base, case_code='CA-001-B')]
        make_excel(file, core.CASE_FIELDS, rows)
        core.import_excel(file, db)
        criteria = {"enabled": ["phone", "full_name", "birth_date_raw"]}
        groups = core.find_duplicate_groups('case', db_path=db, criteria=criteria)
        assert len(groups) == 1
        ids = groups[0]['record_ids']

        dismissed_count = core.dismiss_duplicate_pairs('case', ids, db_path=db, actor='tester')
        assert dismissed_count == 1

        groups_after = core.find_duplicate_groups('case', db_path=db, criteria=criteria)
        assert groups_after == []


def test_dismiss_duplicate_pairs_partial_group_keeps_new_member_visible():
    """3 bản ghi cùng khớp tiêu chí — chỉ xác nhận 2 trong số đó KHÔNG trùng, bản thứ 3 vẫn phải
    còn hiện ra (nối với 1 trong 2 bản kia) vì chưa ai xem qua cặp đó."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = root / 'test.db'
        core.BACKUP_DIR = root / 'backups'
        file = root / 'cases.xlsx'
        base = {
            'full_name': 'Nguyễn Văn A', 'birth_date_raw': '01/01/1990', 'gender': 'Nam',
            'phone': '0901234567', 'commune': 'Phường Gia Viên',
            'main_diagnosis': 'Sốt xuất huyết Dengue', 'onset_date': '10/07/2026',
            'report_datetime': '11/07/2026 08:00', 'reporting_unit': 'Trạm Y tế',
        }
        rows = [
            dict(base, case_code='CA-001'), dict(base, case_code='CA-001-B'), dict(base, case_code='CA-001-C'),
        ]
        make_excel(file, core.CASE_FIELDS, rows)
        core.import_excel(file, db)
        criteria = {"enabled": ["phone", "full_name", "birth_date_raw"]}
        groups = core.find_duplicate_groups('case', db_path=db, criteria=criteria)
        assert len(groups) == 1 and groups[0]['record_count'] == 3
        ids = sorted(groups[0]['record_ids'])

        core.dismiss_duplicate_pairs('case', ids[:2], db_path=db, actor='tester')

        groups_after = core.find_duplicate_groups('case', db_path=db, criteria=criteria)
        assert len(groups_after) == 1
        assert set(groups_after[0]['record_ids']) == set(ids)


def test_dismiss_duplicate_pairs_requires_at_least_two_ids():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / 'test.db'
        core.init_db(db)
        assert core.dismiss_duplicate_pairs('case', [1], db_path=db) == 0
        assert core.dismiss_duplicate_pairs('case', [], db_path=db) == 0


def test_dismiss_duplicate_pairs_hides_outbreak_group():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = root / 'test.db'
        file = root / 'outbreaks.xlsx'
        rows = [
            {'disease': 'Bệnh sốt xuất huyết Dengue', 'location': 'Tổ 1 - Phường Gia Viên - Hải Phòng',
             'first_onset_date': '10/07/2026', 'case_count': 2, 'report_datetime': '11/07/2026 08:00',
             'reporting_unit': 'Trạm Y tế Gia Viên'},
            {'disease': 'Sốt xuất huyết Dengue', 'location': 'Tổ 1, Phường Gia Viên, Hải Phòng',
             'first_onset_date': '11/07/2026', 'case_count': 3, 'report_datetime': '12/07/2026 08:00',
             'reporting_unit': 'Trạm Y tế Gia Viên'},
        ]
        make_excel(file, core.OUTBREAK_FIELDS, rows, 'Danh sách ổ dịch')
        core.import_excel(file, db)
        groups = core.find_duplicate_groups('outbreak', db_path=db, min_score=60)
        assert len(groups) == 1
        ids = groups[0]['record_ids']

        core.dismiss_duplicate_pairs('outbreak', ids, db_path=db, actor='tester')
        groups_after = core.find_duplicate_groups('outbreak', db_path=db, min_score=60)
        assert groups_after == []


def test_outbreak_duplicate_detection():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = root / 'test.db'
        file = root / 'outbreaks.xlsx'
        rows = [
            {'disease': 'Bệnh sốt xuất huyết Dengue', 'location': 'Tổ 1 - Phường Gia Viên - Hải Phòng',
             'first_onset_date': '10/07/2026', 'case_count': 2, 'report_datetime': '11/07/2026 08:00',
             'reporting_unit': 'Trạm Y tế Gia Viên'},
            {'disease': 'Sốt xuất huyết Dengue', 'location': 'Tổ 1, Phường Gia Viên, Hải Phòng',
             'first_onset_date': '11/07/2026', 'case_count': 3, 'report_datetime': '12/07/2026 08:00',
             'reporting_unit': 'Trạm Y tế Gia Viên'},
        ]
        make_excel(file, core.OUTBREAK_FIELDS, rows, 'Danh sách ổ dịch')
        assert core.import_excel(file, db).inserted == 2
        groups = core.find_duplicate_groups('outbreak', db_path=db, min_score=60)
        assert groups and groups[0]['record_count'] == 2


def test_deployment_config_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        old = deployment_config.CONFIG_PATH
        deployment_config.CONFIG_PATH = Path(tmp) / 'deployment.json'
        try:
            cfg = deployment_config.DeploymentConfig(server_port=9001, public_url='https://cdc-hp.io.vn')
            deployment_config.save_config(cfg)
            loaded = deployment_config.load_config()
            assert loaded.server_port == 9001
            assert loaded.public_url == 'https://cdc-hp.io.vn'
        finally:
            deployment_config.CONFIG_PATH = old


def test_source_compiles():
    root = Path(__file__).parents[1]
    for name in ('core.py', 'deployment_config.py', 'service_windows.py'):
        compile((root / name).read_text(encoding='utf-8'), name, 'exec')
