import argparse
import json
import os
import sys
import datetime
import requests


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS_PATH = os.path.join(ROOT, "uploader_status.json")


def _notify(msg: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": msg, "disable_web_page_preview": True},
            timeout=8,
        )
    except Exception:
        return


def _parse_kst(s: str):
    # format: YYYY-mm-dd HH:MM:SS KST
    if not s:
        return None
    s = s.replace(" KST", "").strip()
    try:
        dt = datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        return dt
    except Exception:
        return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--max-age-min", type=int, default=90)
    args = p.parse_args()

    if not os.path.exists(STATUS_PATH):
        print(f"[FAIL] status file missing: {STATUS_PATH}")
        _notify(f"🚨 업로더 감시 실패\nstatus 파일 없음: {STATUS_PATH}")
        sys.exit(2)

    with open(STATUS_PATH, "r", encoding="utf-8") as f:
        st = json.load(f) or {}

    ok = bool(st.get("ok", False))
    updated = _parse_kst(st.get("updated_at_kst", ""))
    now = datetime.datetime.now()
    age_min = None if updated is None else (now - updated).total_seconds() / 60.0

    if not ok:
        msg = f"[FAIL] uploader status not ok. code={st.get('exit_code')} msg={st.get('message')}"
        print(msg)
        _notify(f"🚨 업로더 감시 실패\n{msg}")
        sys.exit(3)

    if age_min is None or age_min > args.max_age_min:
        msg = f"[FAIL] uploader status stale. age_min={age_min} max={args.max_age_min}"
        print(msg)
        _notify(f"🚨 업로더 감시 실패\n{msg}")
        sys.exit(4)

    print(f"[OK] uploader healthy. age_min={age_min:.1f}")
    sys.exit(0)


if __name__ == "__main__":
    main()
