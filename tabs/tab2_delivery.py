import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def render_delivery(ana_df):

    st.title("🚛 배송사별 비교 및 추이")

    # --- 기존 TAB2 코드 그대로 시작 ---
    total_compare = ana_df.groupby(['연월_키', '배송사_정제']).size().reset_index(name='완료건수').rename(columns={'배송사_정제': '지역센터'})
    all_months = sorted(total_compare['연월_키'].unique())
    total_len = len(all_months)

    if total_len > 0:

        if 'p_idx' not in st.session_state:
            st.session_state.p_idx = max(0, total_len - 3)

        col_left, col_mid, col_right = st.columns([1,3,1])

        with col_left:
            if st.button("◀ 이전 달", use_container_width=True):
                if st.session_state.p_idx > 0:
                    st.session_state.p_idx -= 1
                    st.rerun()

        with col_right:
            if st.button("다음 달 ▶", use_container_width=True):
                if st.session_state.p_idx < total_len - 1:
                    st.session_state.p_idx += 1
                    st.rerun()

        start_i = st.session_state.p_idx
        end_i = min(start_i + 3, total_len)
        view_months = all_months[start_i:end_i]

        with col_mid:
            st.markdown(f"<h2 style='text-align: center; color: #0077b6;'>📅 {view_months[0]} ~ {view_months[-1]}</h2>", unsafe_allow_html=True)

        df_view = total_compare[total_compare['연월_키'].isin(view_months)].copy()
        monthly_totals = df_view.groupby('연월_키')['완료건수'].sum()

        fig_bar = go.Figure()

        active_centers = [v for v in V_ORDER if v in df_view['지역센터'].unique()]

        colors = px.colors.qualitative.Pastel

        for i, center in enumerate(active_centers):

            center_data = df_view[df_view['지역센터'] == center]

            y_vals = []
            texts = []

            for m in view_months:
                val = center_data[center_data['연월_키'] == m]['완료건수'].sum()
                total = monthly_totals.get(m, 1)
                share = round((val / total) * 100, 1)

                y_vals.append(val)
                texts.append(f"<b>{val}건</b><br>({share}%)")

            fig_bar.add_trace(go.Bar(
                name=center,
                x=[[f"<b>{m}</b><br><span style='color:red;'>[총 합계: {monthly_totals[m]}건]</span>" for m in view_months],
                   [center for _ in view_months]],
                y=y_vals,
                text=texts,
                textposition='outside',
                marker_color=colors[i % len(colors)],
                textfont=dict(size=14, family="Malgun Gothic")
            ))

        fig_bar.update_layout(
            barmode='group',
            margin=dict(t=80, b=150),
            yaxis_title="완료건수",
            legend=dict(orientation="h", yanchor="bottom", y=1.1, xanchor="right", x=1),
            font=dict(family="Malgun Gothic")
        )

        st.plotly_chart(fig_bar, use_container_width=True)

    else:
        st.warning("데이터가 없습니다.")