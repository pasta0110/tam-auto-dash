from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from services.access_log import append_access_log, read_access_logs


def _detect_suspicious(df: pd.DataFrame) -> pd.DataFrame:
    # 60초 내 서로 다른 탭 4개 이상 열람 시 의심 패턴으로 표기
    if df.empty:
        return pd.DataFrame()
    x = df[df["event"] == "view_tab"].copy()
    if x.empty:
        return pd.DataFrame()
    x = x.sort_values("ts")
    out = []
    for uid, g in x.groupby("user_id", dropna=False):
        g = g.reset_index(drop=True)
        for i in range(len(g)):
            t0 = g.loc[i, "ts"]
            t1 = t0 + pd.Timedelta(seconds=60)
            w = g[(g["ts"] >= t0) & (g["ts"] <= t1)]
            uniq_tabs = set(w["detail"].astype(str).tolist())
            if len(uniq_tabs) >= 4:
                out.append(
                    {
                        "user_id": uid,
                        "nickname": g.loc[i, "nickname"],
                        "start_ts": t0,
                        "end_ts": t1,
                        "distinct_tabs_60s": len(uniq_tabs),
                        "tabs": " | ".join(sorted(uniq_tabs)),
                    }
                )
                break
    if not out:
        return pd.DataFrame()
    return pd.DataFrame(out).sort_values("start_ts", ascending=False)


def render(auth_ctx: dict | None = None) -> None:
    st.title("🛠 6. 사용기록 관리")
    st.caption("관리자 전용: 로그인/로그아웃/인증 이벤트 기록")

    auth_ctx = auth_ctx or {}
    auth_user = auth_ctx.get("user") or {}
    auth_sid = auth_ctx.get("sid", "")
    who = {
        "id": str(auth_user.get("id", "")),
        "nickname": str(auth_user.get("nickname", "")),
        "role": str(auth_ctx.get("role", "admin")),
    }

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        limit = st.selectbox("표시 개수", [100, 200, 500, 1000], index=2)
    with col2:
        event_filter = st.selectbox("이벤트", ["전체", "view_tab", "login_success", "logout", "pin_failed", "pin_locked", "session_extended", "whitelist_denied"])
    with col3:
        refresh = st.button("새로고침", use_container_width=True)

    if refresh:
        append_access_log("admin_refresh_logs", user=who, meta={"sid": auth_sid, "detail": f"limit={limit},event={event_filter}"})
        st.rerun()

    rows = read_access_logs(limit=int(limit))
    if not rows:
        st.info("기록이 없습니다.")
        return

    df = pd.DataFrame(rows)
    if "ts_kst" in df.columns:
        df["ts"] = pd.to_datetime(df["ts_kst"].str.replace(" KST", "", regex=False), errors="coerce")
    else:
        df["ts"] = pd.NaT

    # 기간/사용자 필터
    df_users = sorted([u for u in df["user_id"].dropna().astype(str).unique().tolist() if u])
    c4, c5 = st.columns([1, 1])
    with c4:
        user_filter = st.selectbox("사용자", ["전체"] + df_users)
    with c5:
        ts_valid = df["ts"].dropna()
        if not ts_valid.empty:
            min_d = ts_valid.min().date()
            max_d = ts_valid.max().date()
        else:
            min_d = max_d = pd.Timestamp.today().date()
        date_range = st.date_input("기간", value=(min_d, max_d))

    filt = df.copy()
    if event_filter != "전체":
        filt = filt[filt["event"] == event_filter]
    if user_filter != "전체":
        filt = filt[filt["user_id"].astype(str) == str(user_filter)]
    if isinstance(date_range, tuple) and len(date_range) == 2:
        d0 = pd.Timestamp(date_range[0])
        d1 = pd.Timestamp(date_range[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        filt = filt[(filt["ts"].isna()) | ((filt["ts"] >= d0) & (filt["ts"] <= d1))]

    # 관리자 조작 로그
    current_filter_sig = f"{limit}|{event_filter}|{user_filter}|{date_range}"
    if st.session_state.get("tab6_last_filter_sig") != current_filter_sig:
        append_access_log("admin_filter_logs", user=who, meta={"sid": auth_sid, "detail": current_filter_sig})
        st.session_state["tab6_last_filter_sig"] = current_filter_sig

    suspicious = _detect_suspicious(filt)
    if not suspicious.empty:
        st.warning(f"의심 패턴 감지 {len(suspicious)}건 (60초 내 4개+ 탭 열람)")
        st.dataframe(suspicious, use_container_width=True, hide_index=True, height=180)
    else:
        st.info("의심 패턴 없음")

    keep_cols = ["ts_kst", "event", "role", "nickname", "user_id", "sid", "ip", "ua", "detail"]
    cols = [c for c in keep_cols if c in filt.columns]
    view_df = filt[cols].copy()

    st.dataframe(view_df, use_container_width=True, hide_index=True, height=520)

    # xlsx 다운로드
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as xw:
        view_df.to_excel(xw, index=False, sheet_name="logs")
        if not suspicious.empty:
            suspicious.to_excel(xw, index=False, sheet_name="suspicious")
    xlsx_bytes = bio.getvalue()
    if st.download_button(
        "📥 사용기록 다운로드 (xlsx)",
        data=xlsx_bytes,
        file_name="auth_access_logs.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    ):
        append_access_log("admin_download_logs_xlsx", user=who, meta={"sid": auth_sid, "detail": f"rows={len(view_df)}"})
