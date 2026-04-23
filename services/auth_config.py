from __future__ import annotations

import os
from typing import Any

import streamlit as st


def _sget(key: str, default: Any = "") -> Any:
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key, default)


def _to_bool(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}


def _to_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _to_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        return [str(x).strip() for x in v if str(x).strip()]
    raw = str(v).strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def get_auth_settings() -> dict[str, Any]:
    session_minutes = _to_int(_sget("AUTH_SESSION_MINUTES", 10), 10)
    if session_minutes <= 0:
        session_minutes = max(1, _to_int(_sget("AUTH_SESSION_HOURS", 12), 12) * 60)

    cfg = {
        "enabled": _to_bool(_sget("AUTH_ENABLED", False), False),
        "client_id": str(_sget("AUTH_KAKAO_CLIENT_ID", "")).strip(),
        "client_secret": str(_sget("AUTH_KAKAO_CLIENT_SECRET", "")).strip(),
        "redirect_uri": str(_sget("AUTH_KAKAO_REDIRECT_URI", "")).strip(),
        "whitelist_ids": set(_to_list(_sget("AUTH_KAKAO_WHITELIST_IDS", []))),
        "whitelist_emails": set(x.lower() for x in _to_list(_sget("AUTH_KAKAO_WHITELIST_EMAILS", []))),
        "admin_ids": set(_to_list(_sget("AUTH_ADMIN_KAKAO_IDS", []))),
        "admin_emails": set(x.lower() for x in _to_list(_sget("AUTH_ADMIN_KAKAO_WHITELIST_EMAILS", []))),
        "pin_user_code": str(_sget("AUTH_PIN_USER_CODE", _sget("AUTH_PIN_CODE", ""))).strip(),
        "pin_user_sha256": str(_sget("AUTH_PIN_USER_SHA256", _sget("AUTH_PIN_SHA256", ""))).strip().lower(),
        "pin_admin_code": str(_sget("AUTH_PIN_ADMIN_CODE", "")).strip(),
        "pin_admin_sha256": str(_sget("AUTH_PIN_ADMIN_SHA256", "")).strip().lower(),
        "pin_max_attempts": max(1, _to_int(_sget("AUTH_PIN_MAX_ATTEMPTS", 5), 5)),
        "session_minutes": session_minutes,
        "state_secret": str(_sget("AUTH_STATE_SECRET", "")).strip(),
    }
    cfg["whitelist_ids"] = set(cfg["whitelist_ids"]) | set(cfg["admin_ids"])
    return cfg
