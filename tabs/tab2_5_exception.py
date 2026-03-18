import streamlit as st
import pandas as pd

from services.exception_ops import build_exception_pack


def render(delivery_df, ctx, cache_key=None):
    st.title("⚠️ 2.5 운영 예외 큐")
    st.caption("활성 주문상태(주문확정/배송준비/배송중) 기준으로, 정상납기(수도권 3영업일/기타 4영업일) 초과 건만 우선순위화합니다.")
    mobile_mode = str(st.query_params.get("mobile", "0")) == "1"
    if mobile_mode:
        st.caption("모바일 최적화 모드: 핵심 컬럼만 표시")

    state_key = f"tab2_5_exception::{cache_key}::{ctx.get('m_key')}::{ctx.get('yesterday_str')}"
    if state_key not in st.session_state:
        st.session_state[state_key] = build_exception_pack(delivery_df, ctx)
    pack = st.session_state[state_key]
    excluded_count = int(pack.get("excluded_count", 0) or 0)
    if excluded_count > 0:
        st.caption(f"영구 예외 처리 주문번호 제외: {excluded_count}건")

    role = st.radio(
        "화면 모드",
        ["운영자", "센터장", "경영진"],
        horizontal=True,
        key="exc_role_mode",
    )

    k = pack.get("kpi", {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SLA(약속일내 완료율)", f"{k.get('ontime_rate', 0):.2f}%")
    c2.metric("지연(D+1+)", f"{k.get('overdue', 0):,}건")
    c3.metric("48시간 내 위험", f"{k.get('at_risk_48h', 0):,}건")
    c4.metric("기준이내 대기", f"{k.get('within_standard_pending', 0):,}건")
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("D+1", f"{k.get('delay_d1', 0):,}건")
    c6.metric("D+2", f"{k.get('delay_d2', 0):,}건")
    c7.metric("D+3+", f"{k.get('delay_d3p', 0):,}건")
    c8.metric("예외큐 총건", f"{k.get('queue_total', 0):,}건")

    st.subheader("1) 오늘 조치 대상 예외 큐")
    q = pack.get("queue", pd.DataFrame())
    if (role == "운영자") and (q is None or q.empty):
        st.info("현재 기준 예외 큐가 없습니다.")
    elif role == "운영자":
        default_limit = 40 if mobile_mode else 80
        limit = st.slider("표시 건수", min_value=20, max_value=300, value=default_limit, step=20, key="exc_limit")
        qv = q.head(limit).copy()
        if mobile_mode:
            keep_cols = [c for c in ["주문번호", "배송예정일", "기준초과영업일", "리스크구분", "원인태그", "권장조치"] if c in qv.columns]
            if keep_cols:
                qv = qv[keep_cols]
        st.dataframe(qv, use_container_width=True, hide_index=True, height=420)
    elif role in ("센터장", "경영진"):
        top_risk = q.head(20)[["주문번호", "배송예정일", "리스크구분", "배송사_정제", "권장조치"]] if (q is not None and not q.empty) else pd.DataFrame()
        if top_risk.empty:
            st.info("현재 기준 고위험 주문이 없습니다.")
        else:
            st.dataframe(top_risk, use_container_width=True, hide_index=True, height=280)

    if role == "운영자":
        if mobile_mode:
            st.subheader("2) 권역별 원인 분포")
            causes = pack.get("causes", pd.DataFrame())
            if causes is None or causes.empty:
                st.info("원인 분포 데이터가 없습니다.")
            else:
                st.dataframe(causes, use_container_width=True, hide_index=True, height=280)

            st.subheader("3) 원인태그/권장조치 요약")
            cause_tags = pack.get("cause_tags", pd.DataFrame())
            actions = pack.get("actions", pd.DataFrame())
            if cause_tags is not None and not cause_tags.empty:
                st.dataframe(cause_tags.head(8), use_container_width=True, hide_index=True, height=220)
            if actions is not None and not actions.empty:
                st.dataframe(actions.head(8), use_container_width=True, hide_index=True, height=220)

            st.subheader("4) 당월 비정상 이벤트")
            abnormal = pack.get("abnormal", pd.DataFrame())
            if abnormal is None or abnormal.empty:
                st.info("비정상 이벤트 데이터가 없습니다.")
            else:
                st.dataframe(abnormal, use_container_width=True, hide_index=True, height=240)
            st.subheader("5) 동일인 상담메세지 기반 지연원인")
            person_reasons = pack.get("person_reasons", pd.DataFrame())
            if person_reasons is None or person_reasons.empty:
                st.info("동일인 원인 추정 데이터가 없습니다.")
            else:
                st.dataframe(
                    person_reasons[["동일인주문수", "지연원인(메세지추정)", "상담메세지요약"]].head(10),
                    use_container_width=True,
                    hide_index=True,
                    height=260,
                )
        else:
            col_l, col_r = st.columns(2)
            with col_l:
                st.subheader("2) 권역별 원인 분포")
                causes = pack.get("causes", pd.DataFrame())
                if causes is None or causes.empty:
                    st.info("원인 분포 데이터가 없습니다.")
                else:
                    st.dataframe(causes, use_container_width=True, hide_index=True, height=320)

            with col_r:
                st.subheader("3) 원인태그/권장조치 요약")
                cause_tags = pack.get("cause_tags", pd.DataFrame())
                actions = pack.get("actions", pd.DataFrame())
                if cause_tags is None or cause_tags.empty:
                    st.info("원인태그 요약 데이터가 없습니다.")
                else:
                    st.dataframe(cause_tags.head(10), use_container_width=True, hide_index=True, height=150)
                if actions is None or actions.empty:
                    st.info("권장조치 요약 데이터가 없습니다.")
                else:
                    st.dataframe(actions.head(10), use_container_width=True, hide_index=True, height=150)

            st.subheader("4) 당월 비정상 이벤트")
            abnormal = pack.get("abnormal", pd.DataFrame())
            if abnormal is None or abnormal.empty:
                st.info("비정상 이벤트 데이터가 없습니다.")
            else:
                st.dataframe(abnormal, use_container_width=True, hide_index=True, height=220)
            st.subheader("5) 동일인 상담메세지 기반 지연원인")
            person_reasons = pack.get("person_reasons", pd.DataFrame())
            if person_reasons is None or person_reasons.empty:
                st.info("동일인 원인 추정 데이터가 없습니다.")
            else:
                st.dataframe(
                    person_reasons[["동일인주문수", "지연원인(메세지추정)", "상담메세지요약"]].head(20),
                    use_container_width=True,
                    hide_index=True,
                    height=240,
                )

    if role == "센터장":
        st.subheader("2) 센터별 SLA/예외")
        center_sla = pack.get("center_sla", pd.DataFrame())
        if center_sla is None or center_sla.empty:
            st.info("센터 SLA 데이터가 없습니다.")
        else:
            st.dataframe(center_sla, use_container_width=True, hide_index=True, height=320)
        st.subheader("3) 내일 병목 경보")
        capacity_warning = pack.get("capacity_warning", pd.DataFrame())
        if capacity_warning is None or capacity_warning.empty:
            st.success("내일 과부하 경보가 없습니다.")
        else:
            st.dataframe(capacity_warning, use_container_width=True, hide_index=True, height=220)

    if role == "경영진":
        left, right = st.columns(2)
        with left:
            st.subheader("2) 센터별 SLA 하위")
            center_sla = pack.get("center_sla", pd.DataFrame())
            if center_sla is None or center_sla.empty:
                st.info("센터 SLA 데이터가 없습니다.")
            else:
                st.dataframe(center_sla.head(8), use_container_width=True, hide_index=True, height=260)
        with right:
            st.subheader("3) 핵심 조치 Top")
            actions = pack.get("actions", pd.DataFrame())
            if actions is None or actions.empty:
                st.info("핵심 조치 데이터가 없습니다.")
            else:
                st.dataframe(actions.head(8), use_container_width=True, hide_index=True, height=260)
        st.subheader("4) 내일 병목 경보")
        capacity_warning = pack.get("capacity_warning", pd.DataFrame())
        if capacity_warning is None or capacity_warning.empty:
            st.success("내일 과부하 경보가 없습니다.")
        else:
            st.dataframe(capacity_warning, use_container_width=True, hide_index=True, height=200)

    st.info(
        "권장 운영 액션: "
        "중대지연 에스컬레이션 → 지연건 배송사 ETA 확정 → 당일 미완료 재배차"
    )
