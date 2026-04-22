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
import streamlit.components.v1 as components

from services.access_log import append_access_log
from services.notifiers import build_telegram_notifier


SESSION_AUTH = "auth_ok"
SESSION_AUTH_USER = "auth_user"
SESSION_AUTH_UNTIL = "auth_until"
SESSION_AUTH_ROLE = "auth_role"
SESSION_AUTH_SID = "auth_sid"
SESSION_OAUTH_STATE = "auth_oauth_state"
SESSION_PENDING_USER = "auth_pending_user"
SESSION_PIN_ATTEMPTS = "auth_pin_attempts"
SESSION_WHITELIST_ALERTED_UID = "auth_whitelist_alerted_uid"
SESSION_ACCESS_LOGGED = "auth_access_logged"
SESSION_COUNTDOWN_GEN = "auth_countdown_gen"
SESSION_LAST_SECURITY_SIGNAL = "auth_last_security_signal"


def _new_countdown_generation() -> int:
    return int(time.time() * 1000)


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


def _client_meta_dict() -> dict[str, str]:
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


def _drop_query_params(keys: list[str]) -> None:
    try:
        for k in keys:
            if k in st.query_params:
                del st.query_params[k]
    except Exception:
        pass


def _consume_security_signal(user: dict[str, Any], sid: str) -> None:
    ev = str(st.query_params.get("sec_event", "")).strip().lower()
    if not ev:
        return

    key_name = str(st.query_params.get("sec_key", "")).strip()[:80]
    client_ts = str(st.query_params.get("sec_ts", "")).strip()[:32]
    signal_key = f"{ev}|{key_name}|{client_ts}"
    if st.session_state.get(SESSION_LAST_SECURITY_SIGNAL) == signal_key:
        _drop_query_params(["sec_event", "sec_key", "sec_ts"])
        return

    st.session_state[SESSION_LAST_SECURITY_SIGNAL] = signal_key
    meta = {
        **_client_meta_dict(),
        "sid": sid or "",
        "event": ev,
        "key": key_name or "-",
        "client_ts": client_ts or "-",
    }
    append_access_log("suspicious_key", user=user, meta=meta)

    if _to_bool(_sget("AUTH_SECURITY_KEY_NOTIFY", False), False):
        _notify("suspicious_key", f"user={user}\n{_client_meta()}\nevent={ev}\nkey={key_name}\nclient_ts={client_ts}")

    _drop_query_params(["sec_event", "sec_key", "sec_ts"])
    st.rerun()


def render_live_session_countdown(until_ts: float, label: str = "🔐 세션 남은 시간", generation: int = 0) -> None:
    try:
        end_ms = int(float(until_ts) * 1000)
    except Exception:
        return
    comp_id = f"session-countdown-{generation}-{end_ms}"
    safe_label = (label or "세션 남은 시간").replace("'", "\\'")
    html = f"""
    <div id="{comp_id}" style="font-size:13px;color:#6b7280;"></div>
    <script>
    (function() {{
      const endMs = {end_ms};
      const el = document.getElementById('{comp_id}');
      function pad(n) {{ return String(n).padStart(2, '0'); }}
      function tick() {{
        const now = Date.now();
        let remain = Math.max(0, Math.floor((endMs - now) / 1000));
        const mm = Math.floor(remain / 60);
        const ss = remain % 60;
        if (el) {{
          el.textContent = '{safe_label}: ' + pad(mm) + ':' + pad(ss);
        }}
      }}
      tick();
      setInterval(tick, 1000);
    }})();
    </script>
    """
    components.html(html, height=28)


def render_session_popup_and_autologout(until_ts: float, generation: int = 0) -> None:
    try:
        end_ms = int(float(until_ts) * 1000)
    except Exception:
        return
    comp_id = f"session-guard-{generation}-{end_ms}"
    html = f"""
    <div id="{comp_id}" style="display:none;"></div>
    <script>
    (function() {{
      const endMs = {end_ms};
      const popupKey = "session_popup_" + endMs + "_{generation}";

      function withParam(url, key, value) {{
        const u = new URL(url, window.location.origin);
        u.searchParams.set(key, value);
        return u.toString();
      }}

      function tick() {{
        const now = Date.now();
        const remain = Math.floor((endMs - now) / 1000);

        if (remain <= 0) {{
          // 만료 시 자동 로그아웃 트리거
          window.location.replace(withParam(window.location.href, "force_logout", "1"));
          return;
        }}

        if (remain <= 60 && !sessionStorage.getItem(popupKey)) {{
          sessionStorage.setItem(popupKey, "1");
          const ok = window.confirm("세션이 1분 내 만료됩니다. 로그인 시간을 연장할까요?");
          if (ok) {{
            window.location.replace(withParam(window.location.href, "extend_session", "1"));
            return;
          }}
        }}
      }}

      tick();
      setInterval(tick, 1000);
    }})();
    </script>
    """
    components.html(html, height=0)


def render_capture_guard() -> None:
    enabled = _to_bool(_sget("AUTH_CAPTURE_GUARD_ENABLED", True), True)
    if not enabled:
        return
    html = """
    <script>
    (function() {
      try {
        const d = window.parent && window.parent.document ? window.parent.document : document;
        if (!d || d.getElementById("capture-guard-installed")) return;

        const mark = d.createElement("div");
        mark.id = "capture-guard-installed";
        mark.style.display = "none";
        d.body.appendChild(mark);

        const overlay = d.createElement("div");
        overlay.id = "capture-guard-overlay";
        overlay.style.position = "fixed";
        overlay.style.inset = "0";
        overlay.style.background = "#ffffff";
        overlay.style.zIndex = "2147483647";
        overlay.style.display = "none";
        overlay.style.alignItems = "center";
        overlay.style.justifyContent = "center";
        overlay.style.flexDirection = "column";
        overlay.style.fontFamily = "Arial, sans-serif";
        overlay.style.color = "#111827";
        overlay.style.gap = "12px";

        const msg = d.createElement("div");
        msg.textContent = "보안 경고: 캡처 키가 감지되어 화면이 가려졌습니다.";
        msg.style.fontSize = "18px";
        msg.style.fontWeight = "700";

        const sub = d.createElement("div");
        sub.textContent = "외부 공유는 금지되어 있습니다.";
        sub.style.fontSize = "14px";

        const btn = d.createElement("button");
        btn.textContent = "화면 복구";
        btn.style.padding = "10px 16px";
        btn.style.border = "1px solid #111827";
        btn.style.background = "#fff";
        btn.style.cursor = "pointer";
        btn.onclick = function() { overlay.style.display = "none"; };

        overlay.appendChild(msg);
        overlay.appendChild(sub);
        overlay.appendChild(btn);
        d.body.appendChild(overlay);

        function triggerGuard() {
          overlay.style.display = "flex";
          try { window.parent.alert("캡처 키(PrintScreen)가 감지되었습니다."); } catch (e) {}
        }

        function reportSecuritySignal(eventName, keyName) {
          try {
            const u = new URL(window.location.href);
            u.searchParams.set("sec_event", eventName);
            u.searchParams.set("sec_key", keyName);
            u.searchParams.set("sec_ts", String(Date.now()));
            window.location.replace(u.toString());
          } catch (e) {
            // no-op
          }
        }

        d.addEventListener("keydown", function(e) {
          const k = (e && e.key) ? String(e.key) : "";
          const code = (e && e.keyCode) ? Number(e.keyCode) : 0;
          if (k === "PrintScreen" || code === 44) {
            triggerGuard();
            reportSecuritySignal("capture_key", "PrintScreen");
            e.preventDefault();
          }
        }, true);
      } catch (err) {
        // no-op
      }
    })();
    </script>
    """
    components.html(html, height=0)


def render_interaction_guard() -> None:
    enabled = _to_bool(_sget("AUTH_INTERACTION_GUARD_ENABLED", True), True)
    if not enabled:
        return
    html = """
    <script>
    (function() {
      try {
        const d = window.parent && window.parent.document ? window.parent.document : document;
        if (!d || d.getElementById("interaction-guard-installed")) return;

        const mark = d.createElement("div");
        mark.id = "interaction-guard-installed";
        mark.style.display = "none";
        d.body.appendChild(mark);

        const style = d.createElement("style");
        style.id = "interaction-guard-style";
        style.textContent = `
          html, body, [data-testid="stAppViewContainer"] {
            -webkit-user-select: none !important;
            -moz-user-select: none !important;
            -ms-user-select: none !important;
            user-select: none !important;
            -webkit-touch-callout: none !important;
          }
          img, svg, canvas {
            -webkit-user-drag: none !important;
            user-drag: none !important;
          }
        `;
        d.head.appendChild(style);

        const block = function(e) {
          if (!e) return;
          e.preventDefault();
          e.stopPropagation();
          return false;
        };

        d.addEventListener("contextmenu", block, true);
        d.addEventListener("dragstart", block, true);
        d.addEventListener("selectstart", block, true);
      } catch (err) {
        // no-op
      }
    })();
    </script>
    """
    components.html(html, height=0)


def _settings() -> dict[str, Any]:
    session_minutes = _to_int(_sget("AUTH_SESSION_MINUTES", 10), 10)
    if session_minutes <= 0:
        # backward compatibility
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
        # 요청 기본값: 일반 351037, 관리자 144883
        "pin_user_code": str(_sget("AUTH_PIN_USER_CODE", _sget("AUTH_PIN_CODE", "351037"))).strip(),
        "pin_user_sha256": str(_sget("AUTH_PIN_USER_SHA256", _sget("AUTH_PIN_SHA256", ""))).strip().lower(),
        "pin_admin_code": str(_sget("AUTH_PIN_ADMIN_CODE", "144883")).strip(),
        "pin_admin_sha256": str(_sget("AUTH_PIN_ADMIN_SHA256", "")).strip().lower(),
        "pin_max_attempts": max(1, _to_int(_sget("AUTH_PIN_MAX_ATTEMPTS", 5), 5)),
        "session_minutes": session_minutes,
        "state_secret": str(_sget("AUTH_STATE_SECRET", "")).strip(),
    }
    # 관리자 ID는 화이트리스트에도 자동 포함되게 처리
    cfg["whitelist_ids"] = set(cfg["whitelist_ids"]) | set(cfg["admin_ids"])
    return cfg


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


def _build_kakao_login_url(
    client_id: str,
    redirect_uri: str,
    state: str,
    through_account: bool = False,
    prompt_login: bool = False,
) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        # account_email 권한이 없는 앱에서도 동작하도록 최소 scope만 사용
        "scope": "profile_nickname",
    }
    if through_account:
        params["through_account"] = "true"
    if prompt_login:
        params["prompt"] = "login"
    q = urlencode(params)
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


def _get_role(user: dict[str, str], admin_ids: set[str], admin_emails: set[str]) -> str:
    uid = user.get("id", "")
    email = user.get("email", "").lower()
    if (uid and uid in admin_ids) or (email and email in admin_emails):
        return "admin"
    return "user"


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


def _clear_auth_runtime_only() -> None:
    # 콜백 직후 PIN 대기 상태(SESSION_PENDING_USER)는 유지해야 하므로
    # 루프 방지를 위해 pending을 제외한 런타임 인증 정보만 정리한다.
    for k in [SESSION_AUTH, SESSION_AUTH_USER, SESSION_AUTH_UNTIL, SESSION_AUTH_ROLE, SESSION_AUTH_SID, SESSION_PIN_ATTEMPTS, SESSION_ACCESS_LOGGED, SESSION_COUNTDOWN_GEN, SESSION_LAST_SECURITY_SIGNAL, "last_view_logged"]:
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


def enforce_auth_gate() -> None:
    cfg = _settings()
    if not cfg["enabled"]:
        return

    # query-param control hooks from client-side popup/autologout
    q_force = str(st.query_params.get("force_logout", "")).strip() == "1"
    q_extend = str(st.query_params.get("extend_session", "")).strip() == "1"
    if q_force:
        if st.session_state.get(SESSION_AUTH_USER):
            append_access_log("session_expired_logout", user=st.session_state.get(SESSION_AUTH_USER), meta={**_client_meta_dict(), "sid": st.session_state.get(SESSION_AUTH_SID, "")})
        _clear_auth()
        try:
            st.query_params.clear()
        except Exception:
            pass
        st.rerun()
    if q_extend and st.session_state.get(SESSION_AUTH):
        st.session_state[SESSION_AUTH_UNTIL] = time.time() + (cfg["session_minutes"] * 60)
        st.session_state[SESSION_COUNTDOWN_GEN] = _new_countdown_generation()
        append_access_log("session_extended", user=st.session_state.get(SESSION_AUTH_USER), meta={**_client_meta_dict(), "sid": st.session_state.get(SESSION_AUTH_SID, "")})
        _notify("session_extended", _client_meta())
        try:
            st.query_params.clear()
        except Exception:
            pass
        st.rerun()

    # already authed and alive
    if st.session_state.get(SESSION_AUTH) and time.time() < float(st.session_state.get(SESSION_AUTH_UNTIL, 0)):
        user = st.session_state.get(SESSION_AUTH_USER) or {}
        sid = str(st.session_state.get(SESSION_AUTH_SID, ""))
        _consume_security_signal(user=user, sid=sid)
        if not st.session_state.get(SESSION_ACCESS_LOGGED):
            append_access_log(
                "dashboard_access",
                user={**user, "role": st.session_state.get(SESSION_AUTH_ROLE, "user")},
                meta={**_client_meta_dict(), "sid": sid},
            )
            st.session_state[SESSION_ACCESS_LOGGED] = True
        with st.sidebar:
            st.caption(f"🔐 로그인: {user.get('nickname') or user.get('email') or user.get('id')}")
            st.caption(f"🛡 권한: {'관리자' if st.session_state.get(SESSION_AUTH_ROLE) == 'admin' else '일반'}")
            generation = int(st.session_state.get(SESSION_COUNTDOWN_GEN, 0))
            render_live_session_countdown(
                st.session_state.get(SESSION_AUTH_UNTIL, 0),
                label="⏱ 세션",
                generation=generation,
            )
            render_session_popup_and_autologout(
                st.session_state.get(SESSION_AUTH_UNTIL, 0),
                generation=generation,
            )
            render_interaction_guard()
            render_capture_guard()
            if st.button("로그아웃", key="auth_logout_btn"):
                append_access_log(
                    "logout",
                    user={**user, "role": st.session_state.get(SESSION_AUTH_ROLE, "user")},
                    meta={**_client_meta_dict(), "sid": st.session_state.get(SESSION_AUTH_SID, "")},
                )
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
            append_access_log("whitelist_denied", user=user, meta={**_client_meta_dict(), "detail": "not in whitelist"})
            st.error(
                "화이트리스트에 없는 계정입니다.\n"
                f"카카오ID: {user.get('id','-')} / 닉네임: {user.get('nickname','-')}\n"
                "이 ID를 AUTH_KAKAO_WHITELIST_IDS에 추가하세요."
            )
            st.code(f'AUTH_KAKAO_WHITELIST_IDS = ["{user.get("id","")}", ...]', language="toml")
            _notify("whitelist_denied", f"user={user}\n{_client_meta()}")
            st.stop()

        role = _get_role(user, cfg["admin_ids"], cfg["admin_emails"])
        st.session_state[SESSION_PENDING_USER] = {**user, "role": role}
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

        base_role = str((pending or {}).get("role", "user"))
        user_pin_code = cfg["pin_user_code"]
        user_pin_sha256 = cfg["pin_user_sha256"]
        admin_pin_code = cfg["pin_admin_code"]
        admin_pin_sha256 = cfg["pin_admin_sha256"]

        if base_role == "admin":
            if not ((user_pin_code or user_pin_sha256) and (admin_pin_code or admin_pin_sha256)):
                st.error("관리자/일반 PIN 설정이 누락되었습니다. AUTH_PIN_USER_CODE / AUTH_PIN_ADMIN_CODE(또는 *_SHA256)를 설정하세요.")
                st.stop()
            st.caption("관리자 계정은 PIN으로 권한을 선택할 수 있습니다.")
        else:
            if not (user_pin_code or user_pin_sha256):
                st.error("일반 PIN 설정이 없습니다. AUTH_PIN_USER_CODE(또는 AUTH_PIN_USER_SHA256)를 설정하세요.")
                st.stop()

        if base_role == "admin":
            pin_role_hint = "권한 선택 PIN"
        else:
            pin_role_hint = "PIN"

        if base_role != "admin" and not (user_pin_code or user_pin_sha256):
            st.error("PIN 설정이 없습니다. AUTH_PIN_USER_CODE(또는 AUTH_PIN_USER_SHA256)를 설정하세요.")
            st.stop()

        attempts = int(st.session_state.get(SESSION_PIN_ATTEMPTS, 0))
        if attempts >= cfg["pin_max_attempts"]:
            st.error("PIN 실패 5회 초과로 잠금되었습니다. 관리자에게 문의하세요.")
            append_access_log("pin_locked", user=pending, meta={**_client_meta_dict()})
            _notify("pin_locked", f"user={pending}\n{_client_meta()}")
            st.stop()

        pin_input = st.text_input(pin_role_hint, type="password", key="auth_pin_input")
        c1, c2 = st.columns([1, 1])
        with c1:
            verify = st.button("인증 확인", key="auth_pin_verify")
        with c2:
            cancel = st.button("취소", key="auth_pin_cancel")

        if cancel:
            _clear_auth()
            st.rerun()

        if verify:
            login_role = "user"
            verified = False
            if base_role == "admin":
                if _verify_pin(pin_input, admin_pin_code, admin_pin_sha256):
                    verified = True
                    login_role = "admin"
                elif _verify_pin(pin_input, user_pin_code, user_pin_sha256):
                    verified = True
                    login_role = "user"
            else:
                if _verify_pin(pin_input, user_pin_code, user_pin_sha256):
                    verified = True
                    login_role = "user"

            if verified:
                sid = secrets.token_hex(4)
                st.session_state[SESSION_AUTH] = True
                st.session_state[SESSION_AUTH_USER] = pending
                st.session_state[SESSION_AUTH_ROLE] = login_role
                st.session_state[SESSION_AUTH_SID] = sid
                st.session_state[SESSION_AUTH_UNTIL] = time.time() + (cfg["session_minutes"] * 60)
                st.session_state[SESSION_PIN_ATTEMPTS] = 0
                st.session_state[SESSION_ACCESS_LOGGED] = False
                st.session_state[SESSION_COUNTDOWN_GEN] = _new_countdown_generation()
                if SESSION_PENDING_USER in st.session_state:
                    del st.session_state[SESSION_PENDING_USER]
                append_access_log("login_success", user={**pending, "role": login_role}, meta={**_client_meta_dict(), "sid": sid, "mode": login_role})
                _notify("login_success", f"user={pending}\nmode={login_role}\n{_client_meta()}")
                st.rerun()
            else:
                st.session_state[SESSION_PIN_ATTEMPTS] = attempts + 1
                left = max(0, cfg["pin_max_attempts"] - st.session_state[SESSION_PIN_ATTEMPTS])
                if left == 0:
                    st.error("PIN 실패 5회 초과로 잠금되었습니다. 관리자에게 문의하세요.")
                else:
                    st.error(f"PIN 불일치 (남은 시도: {left})")
                append_access_log("pin_failed", user=pending, meta={**_client_meta_dict(), "detail": f"remain={left}"})
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
    # 기본: 브라우저 계정 로그인 강제 (모바일 간편로그인 세션/네트워크 오류 회피)
    login_url = _build_kakao_login_url(
        cfg["client_id"], cfg["redirect_uri"], state, through_account=True, prompt_login=True
    )
    st.title("🔐 보안 로그인")
    st.write("이 대시보드는 승인된 사용자만 접근할 수 있습니다.")
    st.link_button("카카오계정으로 로그인 (권장)", login_url, use_container_width=True)
    kakao_logout_url = "https://accounts.kakao.com/weblogin/account"
    st.link_button("카카오 로그아웃 (테스트용)", kakao_logout_url, use_container_width=True)
    st.caption("로그인 후 화이트리스트 + PIN 인증을 통과해야 대시보드가 열립니다.")
    st.stop()
