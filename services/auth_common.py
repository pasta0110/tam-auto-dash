from __future__ import annotations

import time
from typing import Any

import streamlit as st

from services.access_log import append_access_log
from services.auth_config import _sget, _to_bool
from services.auth_consts import SESSION_LAST_SECURITY_SIGNAL, SESSION_WHITELIST_ALERTED_UID
from services.notifiers import build_telegram_notifier


def client_meta() -> str:
    ip = "-"
    ua = "-"
    try:
        headers = getattr(st.context, "headers", None)
        if headers:
            xff = headers.get("x-forwarded-for", "")
            if xff:
                ip = xff.split(",")[0].strip()
            ua = headers.get("user-agent", "-")
    except Exception:
        pass
    return f"ip={ip}, ua={ua[:120]}"


def client_meta_dict() -> dict[str, str]:
    ip = "-"
    ua = "-"
    try:
        headers = getattr(st.context, "headers", None)
        if headers:
            xff = headers.get("x-forwarded-for", "")
            if xff:
                ip = xff.split(",")[0].strip()
            ua = headers.get("user-agent", "-")
    except Exception:
        pass
    return {"ip": ip, "ua": ua[:500]}


def notify(event: str, detail: str) -> None:
    token = str(_sget("TELEGRAM_BOT_TOKEN", "")).strip()
    chat_id = str(_sget("TELEGRAM_CHAT_ID", "")).strip()
    notifier = build_telegram_notifier(token, chat_id)
    if not token or not chat_id:
        return
    notifier.send(f"🔐 인증로그 [{event}]\n{detail}")


def notify_whitelist_request_once(user: dict[str, str]) -> None:
    uid = (user.get("id") or "").strip()
    if not uid:
        return
    if st.session_state.get(SESSION_WHITELIST_ALERTED_UID) == uid:
        return
    st.session_state[SESSION_WHITELIST_ALERTED_UID] = uid
    detail = (
        "미승인 계정 로그인 시도\n"
        f"kakao_id={uid}\n"
        f"nickname={user.get('nickname','-')}\n"
        f"email={user.get('email','-')}\n"
        f"{client_meta()}\n\n"
        "승인 방법(secrets):\n"
        f'AUTH_KAKAO_WHITELIST_IDS = ["{uid}", ...]'
    )
    notify("approve_request", detail)


def drop_query_params(keys: list[str]) -> None:
    try:
        for k in keys:
            if k in st.query_params:
                del st.query_params[k]
    except Exception:
        pass


def consume_security_signal(user: dict[str, Any], sid: str) -> None:
    ev = str(st.query_params.get("sec_event", "")).strip().lower()
    if not ev:
        return

    key_name = str(st.query_params.get("sec_key", "")).strip()[:80]
    client_ts = str(st.query_params.get("sec_ts", "")).strip()[:32]
    signal_key = f"{ev}|{key_name}|{client_ts}"
    if st.session_state.get(SESSION_LAST_SECURITY_SIGNAL) == signal_key:
        drop_query_params(["sec_event", "sec_key", "sec_ts"])
        return

    st.session_state[SESSION_LAST_SECURITY_SIGNAL] = signal_key
    detail = f"event={ev},key={key_name or '-'},client_ts={client_ts or '-'}"
    meta = {
        **client_meta_dict(),
        "sid": sid or "",
        "detail": detail,
    }
    append_access_log("suspicious_key", user=user, meta=meta)

    if _to_bool(_sget("AUTH_SECURITY_KEY_NOTIFY", False), False):
        notify("suspicious_key", f"user={user}\n{client_meta()}\n{detail}")

    drop_query_params(["sec_event", "sec_key", "sec_ts"])
    st.rerun()


def new_countdown_generation() -> int:
    return int(time.time() * 1000)
