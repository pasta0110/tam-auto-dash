from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

KST = timezone(timedelta(hours=9))


def _log_path() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_dir = os.path.join(base_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, "auth_access_log.jsonl")


def append_access_log(event: str, user: dict[str, Any] | None = None, meta: dict[str, Any] | None = None) -> None:
    record = {
        "ts_kst": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST"),
        "event": str(event or "").strip() or "unknown",
        "user_id": str((user or {}).get("id", "")).strip(),
        "nickname": str((user or {}).get("nickname", "")).strip(),
        "email": str((user or {}).get("email", "")).strip(),
        "role": str((user or {}).get("role", "")).strip(),
        "sid": str((meta or {}).get("sid", "")).strip(),
        "ip": str((meta or {}).get("ip", "")).strip(),
        "ua": str((meta or {}).get("ua", "")).strip(),
        "detail": str((meta or {}).get("detail", "")).strip(),
    }
    with open(_log_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_access_logs(limit: int = 500) -> list[dict[str, Any]]:
    path = _log_path()
    if not os.path.exists(path):
        return []
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    if limit > 0:
        rows = rows[-limit:]
    rows.reverse()
    return rows
