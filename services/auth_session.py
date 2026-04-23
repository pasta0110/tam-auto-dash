from __future__ import annotations

from typing import Any

import streamlit as st

from services.auth_consts import (
    SESSION_ACCESS_LOGGED,
    SESSION_AUTH,
    SESSION_AUTH_ROLE,
    SESSION_AUTH_SID,
    SESSION_AUTH_UNTIL,
    SESSION_AUTH_USER,
    SESSION_COUNTDOWN_GEN,
    SESSION_LAST_SECURITY_SIGNAL,
    SESSION_PENDING_USER,
    SESSION_PIN_ATTEMPTS,
)


def clear_auth() -> None:
    for k in [
        SESSION_AUTH,
        SESSION_AUTH_USER,
        SESSION_AUTH_UNTIL,
        SESSION_AUTH_ROLE,
        SESSION_AUTH_SID,
        SESSION_PENDING_USER,
        SESSION_PIN_ATTEMPTS,
        SESSION_ACCESS_LOGGED,
        SESSION_COUNTDOWN_GEN,
        SESSION_LAST_SECURITY_SIGNAL,
        "last_view_logged",
    ]:
        if k in st.session_state:
            del st.session_state[k]


def clear_auth_runtime_only() -> None:
    for k in [
        SESSION_AUTH,
        SESSION_AUTH_USER,
        SESSION_AUTH_UNTIL,
        SESSION_AUTH_ROLE,
        SESSION_AUTH_SID,
        SESSION_PIN_ATTEMPTS,
        SESSION_ACCESS_LOGGED,
        SESSION_COUNTDOWN_GEN,
        SESSION_LAST_SECURITY_SIGNAL,
        "last_view_logged",
    ]:
        if k in st.session_state:
            del st.session_state[k]


def get_auth_context() -> dict[str, Any]:
    return {
        "ok": bool(st.session_state.get(SESSION_AUTH)),
        "user": st.session_state.get(SESSION_AUTH_USER) or {},
        "role": str(st.session_state.get(SESSION_AUTH_ROLE, "user")),
        "sid": str(st.session_state.get(SESSION_AUTH_SID, "")),
        "until": float(st.session_state.get(SESSION_AUTH_UNTIL, 0) or 0),
    }


def render_watermark_overlay() -> None:
    ctx = get_auth_context()
    if not ctx["ok"]:
        return
    user = ctx["user"] or {}
    role = ctx["role"]
    sid = ctx["sid"] or "-"
    uid = user.get("id", "-")
    nick = user.get("nickname", "-")
    txt = f"내부전용 | {role} | {nick}({uid}) | sid:{sid} | 외부공유 금지"
    safe_txt = txt.replace("'", "\\'")
    st.markdown(
        f"""
        <style>
        .wm-grid {{
          position: fixed;
          inset: 0;
          pointer-events: none;
          z-index: 999999;
          opacity: 0.10;
          font-size: 14px;
          font-weight: 600;
          color: #111827;
          transform: rotate(-18deg);
          transform-origin: center;
          display: grid;
          grid-template-columns: repeat(5, 1fr);
          row-gap: 84px;
          column-gap: 48px;
          padding: 80px 24px;
        }}
        .wm-item {{
          white-space: nowrap;
          user-select: none;
        }}
        </style>
        <div class="wm-grid">
          <div class="wm-item">{safe_txt}</div><div class="wm-item">{safe_txt}</div><div class="wm-item">{safe_txt}</div><div class="wm-item">{safe_txt}</div><div class="wm-item">{safe_txt}</div>
          <div class="wm-item">{safe_txt}</div><div class="wm-item">{safe_txt}</div><div class="wm-item">{safe_txt}</div><div class="wm-item">{safe_txt}</div><div class="wm-item">{safe_txt}</div>
          <div class="wm-item">{safe_txt}</div><div class="wm-item">{safe_txt}</div><div class="wm-item">{safe_txt}</div><div class="wm-item">{safe_txt}</div><div class="wm-item">{safe_txt}</div>
          <div class="wm-item">{safe_txt}</div><div class="wm-item">{safe_txt}</div><div class="wm-item">{safe_txt}</div><div class="wm-item">{safe_txt}</div><div class="wm-item">{safe_txt}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
