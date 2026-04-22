from __future__ import annotations

import pandas as pd
import streamlit as st

from services.access_log import read_access_logs


def render() -> None:
    st.title("🛠 6. 사용기록 관리")
    st.caption("관리자 전용: 로그인/로그아웃/인증 이벤트 기록")

    col1, col2 = st.columns([1, 1])
    with col1:
        limit = st.selectbox("표시 개수", [100, 200, 500, 1000], index=2)
    with col2:
        refresh = st.button("새로고침", use_container_width=True)

    if refresh:
        st.rerun()

    rows = read_access_logs(limit=int(limit))
    if not rows:
        st.info("기록이 없습니다.")
        return

    df = pd.DataFrame(rows)
    keep_cols = ["ts_kst", "event", "role", "nickname", "user_id", "sid", "ip", "ua", "detail"]
    cols = [c for c in keep_cols if c in df.columns]
    df = df[cols]

    st.dataframe(df, use_container_width=True, hide_index=True, height=560)
