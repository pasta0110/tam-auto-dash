import streamlit as st
import pandas as pd

from services.exception_ops import build_exception_pack


def render(delivery_df, ctx, cache_key=None):
    st.title("⚠️ 2.5 운영 예외 큐")
    st.caption("활성 주문상태(주문확정/배송준비/배송중) 기준으로, 주문등록일→배송예정일 영업일 계획 대비 지연 리스크를 우선순위화합니다.")

    state_key = f"tab2_5_exception::{cache_key}::{ctx.get('m_key')}::{ctx.get('yesterday_str')}"
    if state_key not in st.session_state:
        st.session_state[state_key] = build_exception_pack(delivery_df, ctx)
    pack = st.session_state[state_key]
    excluded_count = int(pack.get("excluded_count", 0) or 0)
    if excluded_count > 0:
        st.caption(f"영구 예외 처리 주문번호 제외: {excluded_count}건")

    k = pack.get("kpi", {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SLA(약속일내 완료율)", f"{k.get('ontime_rate', 0):.2f}%")
    c2.metric("지연(D+1+)", f"{k.get('overdue', 0):,}건")
    c3.metric("48시간 내 위험", f"{k.get('at_risk_48h', 0):,}건")
    c4.metric("당일 미완료", f"{k.get('due_today', 0):,}건")

    st.subheader("1) 오늘 조치 대상 예외 큐")
    q = pack.get("queue", pd.DataFrame())
    if q is None or q.empty:
        st.info("현재 기준 예외 큐가 없습니다.")
    else:
        limit = st.slider("표시 건수", min_value=20, max_value=300, value=80, step=20, key="exc_limit")
        st.dataframe(q.head(limit), use_container_width=True, hide_index=True, height=420)

    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("2) 권역별 원인 분포")
        causes = pack.get("causes", pd.DataFrame())
        if causes is None or causes.empty:
            st.info("원인 분포 데이터가 없습니다.")
        else:
            st.dataframe(causes, use_container_width=True, hide_index=True, height=320)

    with col_r:
        st.subheader("3) 당월 비정상 이벤트")
        abnormal = pack.get("abnormal", pd.DataFrame())
        if abnormal is None or abnormal.empty:
            st.info("비정상 이벤트 데이터가 없습니다.")
        else:
            st.dataframe(abnormal, use_container_width=True, hide_index=True, height=320)

    st.info(
        "권장 운영 액션: "
        "중대지연 우선 콜백 → 당일 미완료 재배차 → 48시간 위험 물량 선피킹"
    )
