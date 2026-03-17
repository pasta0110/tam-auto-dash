import streamlit as st
from config import V_ORDER

from .charts import dual_axis_figure, paged_bar_figure
from .metrics import REQUIRED_COLS, bar_view_data, build_total_compare_with_snapshot, dual_axis_data, prepare_work_df

TAB2_PAGE_KEY = "tab2_p_idx"
TAB2_CENTER_KEY = "tab2_center"


def render(ana_df, run_meta=None, cache_key=None):
    st.title("🚛 배송사별 비교 및 추이")

    if ana_df is None or ana_df.empty:
        st.warning("데이터가 없습니다.")
        return

    missing_cols = [c for c in REQUIRED_COLS if c not in ana_df.columns]
    if missing_cols:
        st.error(f"필수 컬럼이 없습니다: {', '.join(missing_cols)}")
        return

    work_df = prepare_work_df(ana_df)
    if work_df.empty:
        st.warning("청호나이스 기준 데이터가 없습니다.")
        return

    tab2_cache_key = f"tab2_total_compare::{cache_key}"
    if st.session_state.get("tab2_total_compare_meta") != cache_key or tab2_cache_key not in st.session_state:
        st.session_state[tab2_cache_key] = build_total_compare_with_snapshot(work_df, run_meta=run_meta)
        st.session_state["tab2_total_compare_meta"] = cache_key
    total_compare, all_months = st.session_state[tab2_cache_key]
    total_len = len(all_months)

    if total_len > 0:
        if TAB2_PAGE_KEY not in st.session_state:
            st.session_state[TAB2_PAGE_KEY] = max(0, total_len - 3)

        st.session_state[TAB2_PAGE_KEY] = max(0, min(st.session_state[TAB2_PAGE_KEY], total_len - 1))

        col_left, col_mid, col_right = st.columns([1, 3, 1])
        with col_left:
            if st.button("◀ 이전 달", use_container_width=True):
                if st.session_state[TAB2_PAGE_KEY] > 0:
                    st.session_state[TAB2_PAGE_KEY] -= 1
                    st.rerun()
        with col_right:
            if st.button("다음 달 ▶", use_container_width=True):
                if st.session_state[TAB2_PAGE_KEY] < total_len - 1:
                    st.session_state[TAB2_PAGE_KEY] += 1
                    st.rerun()

        start_i = st.session_state[TAB2_PAGE_KEY]
        end_i = min(start_i + 3, total_len)
        view_months = all_months[start_i:end_i]

        with col_mid:
            st.markdown(
                f"<h2 style='text-align: center; color: #0077b6;'>📅 {view_months[0]} ~ {view_months[-1]}</h2>",
                unsafe_allow_html=True,
            )

        df_view, monthly_totals, month_labels = bar_view_data(total_compare, view_months)
        active_centers = [v for v in V_ORDER if v in df_view["지역센터"].unique()]
        fig_bar = paged_bar_figure(df_view, view_months, month_labels, monthly_totals, active_centers)
        st.plotly_chart(fig_bar, use_container_width=True, key="paged_bar_chart_final")
    else:
        st.warning("데이터가 없습니다.")

    st.divider()

    active_all_centers = [v for v in V_ORDER if v in total_compare["지역센터"].unique()]
    if not active_all_centers:
        st.warning("선택 가능한 배송사가 없습니다.")
        return

    sel_v = st.selectbox("🎯 상세 분석 배송사 선택", active_all_centers, key=TAB2_CENTER_KEY)
    df_combined = dual_axis_data(total_compare, sel_v)
    fig_dual = dual_axis_figure(df_combined, sel_v)
    st.plotly_chart(fig_dual, use_container_width=True, key="dual_axis_chart")
