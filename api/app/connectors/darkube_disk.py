from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings

SOURCE_ID = "darkube_disk"
SOURCE_LABEL = "دیسک پایدار دارکوب"
MOUNT_CANDIDATES = (Path("/data"),)


def resolve_upload_dir(settings: Settings | None = None) -> Path:
    """Same resolution order as production: env UPLOAD_DIR → settings → /app/uploads → api/uploads."""
    raw = (os.environ.get("UPLOAD_DIR") or "").strip()
    if not raw and settings is not None:
        raw = (settings.upload_dir or "").strip()
    if not raw:
        raw = "/app/uploads"
    path = Path(raw)
    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except OSError:
        fallback = Path(__file__).resolve().parents[2] / "uploads"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def _sqlite_file_from_url(database_url: str) -> Path | None:
    url = (database_url or "").strip()
    if "sqlite" not in url.lower() or ":///" not in url:
        return None
    # sqlite+aiosqlite:////data/ganjeh.db → /data/ganjeh.db
    # sqlite+aiosqlite:///./ganjeh.db → ./ganjeh.db
    return Path(url.split(":///", 1)[1])


def _is_writable_dir(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    probe = path / f".ganjeh_write_probe_{os.getpid()}"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _fmt_bytes(n: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    size = float(n)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


def _usage_for(path: Path) -> dict[str, Any] | None:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    used = usage.total - usage.free
    pct = round((used / usage.total) * 100, 1) if usage.total else 0.0
    return {
        "total_bytes": usage.total,
        "used_bytes": used,
        "free_bytes": usage.free,
        "used_percent": pct,
        "label": f"{_fmt_bytes(used)} از {_fmt_bytes(usage.total)} ({pct}٪)",
    }


def _count_files(path: Path) -> int:
    if not path.is_dir():
        return 0
    try:
        return sum(1 for p in path.iterdir() if p.is_file())
    except OSError:
        return 0


class DarkubeDiskConnector:
    """Persistent Darkube PVC (/data) used for SQLite + manual upload files — not live ERP."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.upload_dir = resolve_upload_dir(settings)
        self.db_path = _sqlite_file_from_url(settings.database_url)

    def _pick_mount(self) -> tuple[Path | None, str]:
        # Darkube pods are Linux; on Windows/dev never treat drive-root \data as the PVC.
        if os.name != "nt":
            for candidate in MOUNT_CANDIDATES:
                if candidate.exists() and candidate.is_dir():
                    return candidate, "mount"
        if self.upload_dir.exists():
            return self.upload_dir, "upload_dir"
        return None, "missing"

    async def status(self) -> dict[str, Any]:
        checked_at = datetime.now(timezone.utc).isoformat()
        mount, mode = self._pick_mount()
        if mount is None:
            return {
                "source": SOURCE_ID,
                "label": SOURCE_LABEL,
                "kind": "persistent_storage",
                "ok": False,
                "configured": True,
                "freshness_label": "دیسک پایدار: مسیر داده در دسترس نیست",
                "detail": "نه /data و نه UPLOAD_DIR قابل استفاده نیستند",
                "mount_path": "/data",
                "upload_dir": str(self.upload_dir),
                "mode": mode,
                "related": {"manual_ingest": "/ingest"},
                "checked_at": checked_at,
                "reason_code": "path_missing",
            }

        writable = _is_writable_dir(mount if mode == "mount" else self.upload_dir)
        usage_path = mount if mode == "mount" else self.upload_dir
        usage = _usage_for(usage_path)
        upload_writable = _is_writable_dir(self.upload_dir)
        ok = writable and upload_writable

        if mode == "mount" and ok:
            freshness = "دیسک پایدار دارکوب: متصل و قابل نوشتن"
            detail = f"مونت {mount} و UPLOAD_DIR={self.upload_dir} آماده است"
            reason = None
        elif mode == "upload_dir" and ok:
            freshness = "ذخیره‌سازی محلی (به‌جای مونت /data)"
            detail = (
                "مسیر /data روی این محیط نیست؛ UPLOAD_DIR قابل نوشتن است "
                "(در دارکوب باید /data مونت شود)"
            )
            reason = None
        else:
            freshness = "دیسک پایدار: فقط‌خواندنی یا خطا"
            detail = f"writable={writable}, upload_writable={upload_writable}, mode={mode}"
            reason = "not_writable"

        db_on_disk = False
        if self.db_path is not None:
            try:
                db_on_disk = mode == "mount" and str(self.db_path).startswith(str(mount))
            except Exception:  # noqa: BLE001
                db_on_disk = False

        return {
            "source": SOURCE_ID,
            "label": SOURCE_LABEL,
            "kind": "persistent_storage",
            "ok": ok,
            "configured": True,
            "freshness_label": freshness,
            "detail": detail,
            "note": "منبع فایل‌های آپلود و SQLite — جایگزین سپیدار برای اعداد زنده ERP نیست",
            "mount_path": str(mount) if mode == "mount" else "/data (غایب)",
            "upload_dir": str(self.upload_dir),
            "database_path": str(self.db_path) if self.db_path else None,
            "database_on_persistent_disk": db_on_disk,
            "mode": mode,
            "usage": usage,
            "usage_label": (usage or {}).get("label"),
            "upload_file_count": _count_files(self.upload_dir),
            "related": {
                "manual_ingest": "/ingest",
                "manual_ingest_api": "/api/manual-ingest",
            },
            "checked_at": checked_at,
            "reason_code": reason,
        }
