from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
import base64
from typing import Any
from urllib.parse import urlencode

import requests
import streamlit as st

from services.notifiers import build_telegram_notifier


SESSION_AUTH = "auth_ok"
SESSION_AUTH_USER = "auth_user"
SESSION_AUTH_UNTIL = "auth_until"
SESSION_OAUTH_STATE = "auth_oauth_state"
SESSION_PENDING_USER = "auth_pending_user"
SESSION_PIN_ATTEMPTS = "auth_pin_attempts"
SESSION_WHITELIST_ALERTED_UID = "auth_whitelist_alerted_uid"


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


def _client_meta() -> str:
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


def _notify(event: str, detail: str) -> None:
    token = str(_sget("TELEGRAM_BOT_TOKEN", "")).strip()
    chat_id = str(_sget("TELEGRAM_CHAT_ID", "")).strip()
    notifier = build_telegram_notifier(token, chat_id)
    if not token or not chat_id:
        return
    notifier.send(f"🔐 인증로그 [{event}]\n{detail}")


def _notify_whitelist_request_once(user: dict[str, str]) -> None:
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
        f"{_client_meta()}\n\n"
        "승인 방법(secrets):\n"
        f'AUTH_KAKAO_WHITELIST_IDS = ["{uid}", ...]'
    )
    _notify("approve_request", detail)


def _settings() -> dict[str, Any]:
    return {
        "enabled": _to_bool(_sget("AUTH_ENABLED", False), False),
        "client_id": str(_sget("AUTH_KAKAO_CLIENT_ID", "")).strip(),
        "client_secret": str(_sget("AUTH_KAKAO_CLIENT_SECRET", "")).strip(),
        "redirect_uri": str(_sget("AUTH_KAKAO_REDIRECT_URI", "")).strip(),
        "whitelist_ids": set(_to_list(_sget("AUTH_KAKAO_WHITELIST_IDS", []))),
        "whitelist_emails": set(x.lower() for x in _to_list(_sget("AUTH_KAKAO_WHITELIST_EMAILS", []))),
        "pin_code": str(_sget("AUTH_PIN_CODE", "")).strip(),
        "pin_sha256": str(_sget("AUTH_PIN_SHA256", "")).strip().lower(),
        "pin_max_attempts": _to_int(_sget("AUTH_PIN_MAX_ATTEMPTS", 5), 5),
        "session_hours": _to_int(_sget("AUTH_SESSION_HOURS", 12), 12),
        "state_secret": str(_sget("AUTH_STATE_SECRET", "")).strip(),
    }


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64u_decode(s: str) -> bytes:
    s = s + ("=" * ((4 - len(s) % 4) % 4))
    return base64.urlsafe_b64decode(s.encode("ascii"))


def _make_state_token(secret_key: str) -> str:
    ts = str(int(time.time()))
    nonce = secrets.token_urlsafe(12)
    payload = f"{ts}.{nonce}"
    sig = hmac.new(secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return f"{payload}.{_b64u(sig)}"


def _verify_state_token(token: str, secret_key: str, ttl_sec: int = 900) -> bool:
    try:
        p = (token or "").split(".")
        if len(p) < 3:
            return False
        ts = int(p[0])
        nonce = p[1]
        sig_in = p[2]
        if (int(time.time()) - ts) > ttl_sec:
            return False
        payload = f"{ts}.{nonce}"
        sig = hmac.new(secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
        return hmac.compare_digest(_b64u(sig), sig_in)
    except Exception:
        return False


def _build_kakao_login_url(client_id: str, redirect_uri: str, state: str) -> str:
    q = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            # account_email 권한이 없는 앱에서도 동작하도록 최소 scope만 사용
            "scope": "profile_nickname",
        }
    )
    return f"https://kauth.kakao.com/oauth/authorize?{q}"


def _exchange_token(client_id: str, client_secret: str, redirect_uri: str, code: str) -> str:
    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code": code,
    }
    if client_secret:
        data["client_secret"] = client_secret
    resp = requests.post("https://kauth.kakao.com/oauth/token", data=data, timeout=15)
    resp.raise_for_status()
    token = (resp.json() or {}).get("access_token", "")
    if not token:
        raise RuntimeError("kakao_access_token_missing")
    return token


def _load_kakao_user(access_token: str) -> dict[str, str]:
    resp = requests.get(
        "https://kapi.kakao.com/v2/user/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    resp.raise_for_status()
    body = resp.json() or {}
    acc = body.get("kakao_account") or {}
    profile = acc.get("profile") or {}
    return {
        "id": str(body.get("id") or "").strip(),
        "email": str(acc.get("email") or "").strip().lower(),
        "nickname": str(profile.get("nickname") or "").strip(),
    }


def _is_whitelisted(user: dict[str, str], ids: set[str], emails: set[str]) -> bool:
    if not ids and not emails:
        return False
    uid = user.get("id", "")
    email = user.get("email", "").lower()
    return (uid and uid in ids) or (email and email in emails)


def _verify_pin(pin_input: str, pin_code: str, pin_sha256: str) -> bool:
    pin_input = (pin_input or "").strip()
    if not pin_input:
        return False
    if pin_code:
        return pin_input == pin_code
    if pin_sha256:
        return hashlib.sha256(pin_input.encode("utf-8")).hexdigest().lower() == pin_sha256
    return False


def _clear_auth() -> None:
    for k in [SESSION_AUTH, SESSION_AUTH_USER, SESSION_AUTH_UNTIL, SESSION_PENDING_USER, SESSION_PIN_ATTEMPTS]:
        if k in st.session_state:
            del st.session_state[k]


def _clear_auth_runtime_only() -> None:
    # 콜백 직후 PIN 대기 상태(SESSION_PENDING_USER)는 유지해야 하므로
    # 루프 방지를 위해 pending을 제외한 런타임 인증 정보만 정리한다.
    for k in [SESSION_AUTH, SESSION_AUTH_USER, SESSION_AUTH_UNTIL, SESSION_PIN_ATTEMPTS]:
        if k in st.session_state:
            del st.session_state[k]


def enforce_auth_gate() -> None:
    cfg = _settings()
    if not cfg["enabled"]:
        return

    # already authed and alive
    if st.session_state.get(SESSION_AUTH) and time.time() < float(st.session_state.get(SESSION_AUTH_UNTIL, 0)):
        user = st.session_state.get(SESSION_AUTH_USER) or {}
        with st.sidebar:
            st.caption(f"🔐 로그인: {user.get('nickname') or user.get('email') or user.get('id')}")
            if st.button("로그아웃", key="auth_logout_btn"):
                _clear_auth()
                _notify("logout", _client_meta())
                st.rerun()
        return

    # session expired
    _clear_auth_runtime_only()

    # callback handling
    code = str(st.query_params.get("code", "")).strip()
    state = str(st.query_params.get("state", "")).strip()
    if code:
        state_secret = cfg["state_secret"] or cfg["client_id"] or "kakao-auth"
        if not _verify_state_token(state, state_secret, ttl_sec=900):
            st.error("로그인 검증(state) 실패. 다시 로그인 해주세요.")
            _notify("oauth_state_failed", _client_meta())
            st.stop()
        try:
            token = _exchange_token(cfg["client_id"], cfg["client_secret"], cfg["redirect_uri"], code)
            user = _load_kakao_user(token)
        except Exception as e:
            st.error(f"카카오 인증 처리 실패: {e}")
            _notify("oauth_exchange_failed", f"{_client_meta()}\nerr={e}")
            st.stop()

        if not _is_whitelisted(user, cfg["whitelist_ids"], cfg["whitelist_emails"]):
            _notify_whitelist_request_once(user)
            st.error(
                "화이트리스트에 없는 계정입니다.\n"
                f"카카오ID: {user.get('id','-')} / 닉네임: {user.get('nickname','-')}\n"
                "이 ID를 AUTH_KAKAO_WHITELIST_IDS에 추가하세요."
            )
            st.code(f'AUTH_KAKAO_WHITELIST_IDS = ["{user.get("id","")}", ...]', language="toml")
            _notify("whitelist_denied", f"user={user}\n{_client_meta()}")
            st.stop()

        st.session_state[SESSION_PENDING_USER] = user
        try:
            st.query_params.clear()
        except Exception:
            pass
        st.rerun()

    # pending user -> PIN step
    pending = st.session_state.get(SESSION_PENDING_USER)
    if pending:
        st.title("🔐 2차 인증(PIN)")
        st.info("카카오 인증이 완료되었습니다. PIN을 입력해주세요.")

        if not (cfg["pin_code"] or cfg["pin_sha256"]):
            st.error("PIN 설정이 없습니다. `AUTH_PIN_CODE` 또는 `AUTH_PIN_SHA256`를 설정하세요.")
            st.stop()

        attempts = int(st.session_state.get(SESSION_PIN_ATTEMPTS, 0))
        if attempts >= cfg["pin_max_attempts"]:
            st.error("PIN 실패 횟수 초과. 페이지를 새로고침하고 다시 시도하세요.")
            _notify("pin_locked", f"user={pending}\n{_client_meta()}")
            st.stop()

        pin_input = st.text_input("PIN", type="password", key="auth_pin_input")
        c1, c2 = st.columns([1, 1])
        with c1:
            verify = st.button("인증 확인", key="auth_pin_verify")
        with c2:
            cancel = st.button("취소", key="auth_pin_cancel")

        if cancel:
            _clear_auth()
            st.rerun()

        if verify:
            if _verify_pin(pin_input, cfg["pin_code"], cfg["pin_sha256"]):
                st.session_state[SESSION_AUTH] = True
                st.session_state[SESSION_AUTH_USER] = pending
                st.session_state[SESSION_AUTH_UNTIL] = time.time() + (cfg["session_hours"] * 3600)
                st.session_state[SESSION_PIN_ATTEMPTS] = 0
                if SESSION_PENDING_USER in st.session_state:
                    del st.session_state[SESSION_PENDING_USER]
                _notify("login_success", f"user={pending}\n{_client_meta()}")
                st.rerun()
            else:
                st.session_state[SESSION_PIN_ATTEMPTS] = attempts + 1
                left = max(0, cfg["pin_max_attempts"] - st.session_state[SESSION_PIN_ATTEMPTS])
                st.error(f"PIN 불일치 (남은 시도: {left})")
                _notify("pin_failed", f"user={pending}\nremain={left}\n{_client_meta()}")
        st.stop()

    # first step: show login button
    missing = [k for k, v in [("AUTH_KAKAO_CLIENT_ID", cfg["client_id"]), ("AUTH_KAKAO_REDIRECT_URI", cfg["redirect_uri"])] if not v]
    if missing:
        st.error("인증 설정 누락: " + ", ".join(missing))
        st.stop()

    state_secret = cfg["state_secret"] or cfg["client_id"] or "kakao-auth"
    state = _make_state_token(state_secret)
    st.session_state[SESSION_OAUTH_STATE] = state
    login_url = _build_kakao_login_url(cfg["client_id"], cfg["redirect_uri"], state)

    st.title("🔐 보안 로그인")
    st.write("이 대시보드는 승인된 사용자만 접근할 수 있습니다.")
    st.link_button("카카오로 로그인", login_url, use_container_width=True)
    st.caption("로그인 후 화이트리스트 + PIN 인증을 통과해야 대시보드가 열립니다.")
    st.stop()
