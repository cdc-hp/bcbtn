from __future__ import annotations

import json
import os
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def _user_data_root() -> Path:
    override = os.environ.get("GIAM_SAT_DICH_BENH_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "CDC_HaiPhong" / "GiamSatDichBenh"
    return Path.home() / ".giam_sat_dich_benh"


USER_DATA_DIR = _user_data_root()
LOCAL_BACKUP_DIR = USER_DATA_DIR / "backups"
CONFIG_PATH = USER_DATA_DIR / "backup_policy.json"


@dataclass
class BackupPolicy:
    enabled: bool = True
    interval_hours: int = 24
    keep_daily: int = 7
    keep_weekly: int = 8
    keep_monthly: int = 12
    keep_manual: int = 20
    destination: str = ""
    verify_after_backup: bool = True
    last_backup_at: str = ""

    def normalized(self) -> "BackupPolicy":
        self.interval_hours = max(1, min(24 * 30, int(self.interval_hours)))
        self.keep_daily = max(0, min(365, int(self.keep_daily)))
        self.keep_weekly = max(0, min(260, int(self.keep_weekly)))
        self.keep_monthly = max(0, min(120, int(self.keep_monthly)))
        self.keep_manual = max(1, min(200, int(self.keep_manual)))
        self.destination = str(self.destination or "").strip()
        return self


def load_policy() -> BackupPolicy:
    if not CONFIG_PATH.exists():
        return BackupPolicy()
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return BackupPolicy()
    return BackupPolicy(**{key: raw.get(key, getattr(BackupPolicy(), key)) for key in asdict(BackupPolicy())}).normalized()


def save_policy(policy: BackupPolicy) -> Path:
    policy.normalized()
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = CONFIG_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(asdict(policy), ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(CONFIG_PATH)
    return CONFIG_PATH


def backup_directory(policy: BackupPolicy | None = None) -> Path:
    policy = (policy or load_policy()).normalized()
    target = Path(policy.destination).expanduser() if policy.destination else LOCAL_BACKUP_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target.resolve()


def verify_backup(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return {"ok": False, "message": "File sao lưu không tồn tại hoặc rỗng.", "path": str(path)}
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()
        message = str(result[0] if result else "Không đọc được kết quả kiểm tra")
        ok = message.lower() == "ok"
        tables = int(conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0])
        return {"ok": ok, "message": message, "tables": tables, "size": path.stat().st_size, "path": str(path)}
    except sqlite3.DatabaseError as exc:
        return {"ok": False, "message": str(exc), "path": str(path)}
    finally:
        conn.close()


def create_backup(
    db_path: Path | str,
    *,
    kind: str = "manual",
    policy: BackupPolicy | None = None,
    update_schedule: bool = True,
) -> Path:
    db_path = Path(db_path)
    if not db_path.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
        sqlite3.connect(db_path).close()
    policy = (policy or load_policy()).normalized()
    directory = backup_directory(policy)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_kind = "".join(ch for ch in kind.lower() if ch.isalnum() or ch in "_-") or "manual"
    target = directory / f"gsbtn_{safe_kind}_{stamp}.db"
    source = sqlite3.connect(db_path)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    if policy.verify_after_backup:
        checked = verify_backup(target)
        if not checked["ok"]:
            target.unlink(missing_ok=True)
            raise RuntimeError(f"Bản sao lưu không đạt kiểm tra toàn vẹn: {checked['message']}")
    if update_schedule:
        policy.last_backup_at = datetime.now().isoformat(timespec="seconds")
        save_policy(policy)
    prune_backups(policy)
    return target


def _parse_backup_time(path: Path) -> datetime:
    try:
        parts = path.stem.split("_")
        return datetime.strptime("_".join(parts[-3:-1]), "%Y%m%d_%H%M%S")
    except Exception:
        return datetime.fromtimestamp(path.stat().st_mtime)


def list_backups(policy: BackupPolicy | None = None) -> list[dict[str, Any]]:
    directory = backup_directory(policy)
    rows: list[dict[str, Any]] = []
    for path in directory.glob("gsbtn_*.db"):
        name = path.stem
        kind = "manual"
        if name.startswith("gsbtn_"):
            pieces = name.split("_")
            if len(pieces) >= 4:
                kind = pieces[1]
        rows.append({
            "name": path.name,
            "path": str(path),
            "kind": kind,
            "created_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(sep=" ", timespec="seconds"),
            "size": path.stat().st_size,
        })
    return sorted(rows, key=lambda item: item["created_at"], reverse=True)


def prune_backups(policy: BackupPolicy | None = None) -> None:
    policy = (policy or load_policy()).normalized()
    directory = backup_directory(policy)
    files = sorted(directory.glob("gsbtn_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    keep: set[Path] = set()
    manual = [p for p in files if "_manual_" in p.name or "_before_" in p.name]
    keep.update(manual[: policy.keep_manual])
    auto = [p for p in files if p not in manual]
    daily: set[str] = set()
    weekly: set[str] = set()
    monthly: set[str] = set()
    for path in auto:
        dt = datetime.fromtimestamp(path.stat().st_mtime)
        day_key = dt.strftime("%Y-%m-%d")
        week_key = f"{dt.isocalendar().year}-W{dt.isocalendar().week:02d}"
        month_key = dt.strftime("%Y-%m")
        if len(daily) < policy.keep_daily and day_key not in daily:
            daily.add(day_key); keep.add(path); continue
        if len(weekly) < policy.keep_weekly and week_key not in weekly:
            weekly.add(week_key); keep.add(path); continue
        if len(monthly) < policy.keep_monthly and month_key not in monthly:
            monthly.add(month_key); keep.add(path)
    for path in files:
        if path not in keep:
            path.unlink(missing_ok=True)


def auto_backup_if_due(db_path: Path | str, policy: BackupPolicy | None = None) -> Path | None:
    policy = (policy or load_policy()).normalized()
    if not policy.enabled:
        return None
    last: datetime | None = None
    if policy.last_backup_at:
        try:
            last = datetime.fromisoformat(policy.last_backup_at)
        except ValueError:
            last = None
    if last and datetime.now() - last < timedelta(hours=policy.interval_hours):
        return None
    return create_backup(db_path, kind="auto", policy=policy)


def restore_backup(backup_path: Path | str, db_path: Path | str, policy: BackupPolicy | None = None) -> dict[str, Any]:
    backup_path = Path(backup_path)
    db_path = Path(db_path)
    check = verify_backup(backup_path)
    if not check["ok"]:
        raise ValueError(f"Không thể phục hồi từ bản sao lỗi: {check['message']}")
    safety = create_backup(db_path, kind="before_restore", policy=policy, update_schedule=False)
    temp = db_path.with_suffix(".restore.tmp")
    temp.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(backup_path)
    destination = sqlite3.connect(temp)
    try:
        source.backup(destination)
    finally:
        destination.close(); source.close()
    for suffix in ("-wal", "-shm"):
        Path(str(db_path) + suffix).unlink(missing_ok=True)
    os.replace(temp, db_path)
    restored_check = verify_backup(db_path)
    if not restored_check["ok"]:
        shutil.copy2(safety, db_path)
        raise RuntimeError("Phục hồi thất bại; đã tự khôi phục lại CSDL trước thao tác.")
    return {"restored_from": str(backup_path), "safety_backup": str(safety), "database": str(db_path)}


def backup_health(policy: BackupPolicy | None = None) -> dict[str, Any]:
    policy = (policy or load_policy()).normalized()
    last: datetime | None = None
    if policy.last_backup_at:
        try:
            last = datetime.fromisoformat(policy.last_backup_at)
        except ValueError:
            last = None
    if last is None:
        rows = list_backups(policy)
        if rows:
            try:
                last = datetime.fromisoformat(str(rows[0]["created_at"]))
            except ValueError:
                last = None
    due_at = last + timedelta(hours=policy.interval_hours) if last else None
    overdue = bool(policy.enabled and (due_at is None or datetime.now() > due_at))
    return {
        "enabled": policy.enabled,
        "last_backup_at": last.isoformat(sep=" ", timespec="seconds") if last else "",
        "due_at": due_at.isoformat(sep=" ", timespec="seconds") if due_at else "",
        "overdue": overdue,
        "message": (
            "Chưa có bản sao lưu nào." if last is None
            else (f"Đã quá hạn sao lưu từ {due_at.isoformat(sep=' ', timespec='minutes')}." if overdue
                  else f"Bản gần nhất: {last.isoformat(sep=' ', timespec='minutes')}.")
        ),
    }
