from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import base64
from urllib.parse import urlencode

import requests


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def make_state_token(secret_key: str) -> str:
    ts = str(int(time.time()))
    nonce = secrets.token_urlsafe(12)
    payload = f"{ts}.{nonce}"
    sig = hmac.new(secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return f"{payload}.{_b64u(sig)}"


def verify_state_token(token: str, secret_key: str, ttl_sec: int = 900) -> bool:
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


def build_kakao_login_url(
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
        "scope": "profile_nickname",
    }
    if through_account:
        params["through_account"] = "true"
    if prompt_login:
        params["prompt"] = "login"
    return f"https://kauth.kakao.com/oauth/authorize?{urlencode(params)}"


def exchange_token(client_id: str, client_secret: str, redirect_uri: str, code: str) -> str:
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


def load_kakao_user(access_token: str) -> dict[str, str]:
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


def is_whitelisted(user: dict[str, str], ids: set[str], emails: set[str]) -> bool:
    if not ids and not emails:
        return False
    uid = user.get("id", "")
    email = user.get("email", "").lower()
    return (uid and uid in ids) or (email and email in emails)


def get_role(user: dict[str, str], admin_ids: set[str], admin_emails: set[str]) -> str:
    uid = user.get("id", "")
    email = user.get("email", "").lower()
    if (uid and uid in admin_ids) or (email and email in admin_emails):
        return "admin"
    return "user"


def verify_pin(pin_input: str, pin_code: str, pin_sha256: str) -> bool:
    pin_input = (pin_input or "").strip()
    if not pin_input:
        return False
    if pin_code:
        return pin_input == pin_code
    if pin_sha256:
        return hashlib.sha256(pin_input.encode("utf-8")).hexdigest().lower() == pin_sha256
    return False
