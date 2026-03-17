import json
import os
import time
from datetime import datetime


def now_kst():
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Seoul"))
    except Exception:
        return datetime.now()


def write_json(path: str, payload: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def write_run_meta(path: str, meta: dict):
    try:
        write_json(path, meta)
    except Exception:
        pass


def read_uploader_status(path: str) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}


def write_uploader_status(status_path: str, ok: bool, code: int, message: str, extra: dict | None = None):
    prev = read_uploader_status(status_path)
    prev_failures = int(prev.get("consecutive_failures", 0) or 0)
    next_failures = 0 if ok else (prev_failures + 1)
    payload = {
        "ok": bool(ok),
        "exit_code": int(code),
        "message": str(message),
        "updated_at_kst": now_kst().strftime("%Y-%m-%d %H:%M:%S KST"),
        "log_file": os.getenv("UPLOADER_LOG_FILE", ""),
        "consecutive_failures": next_failures,
    }
    if extra:
        payload.update(extra)
    try:
        write_json(status_path, payload)
    except Exception:
        pass


def acquire_lock(lock_path: str) -> tuple[bool, str]:
    try:
        if os.path.exists(lock_path):
            age = time.time() - os.path.getmtime(lock_path)
            if age < 60 * 60 * 6:
                return False, f"lock exists ({int(age)}s)"
            os.remove(lock_path)
        with open(lock_path, "w", encoding="utf-8") as f:
            f.write(f"{os.getpid()}|{now_kst().strftime('%Y-%m-%d %H:%M:%S KST')}\n")
        return True, "ok"
    except Exception as e:
        return False, str(e)


def release_lock(lock_path: str):
    try:
        if os.path.exists(lock_path):
            os.remove(lock_path)
    except Exception:
        pass
