# tabs/tab2_delivery.py
# 2. 배송사별 분석 (막대, 이중축 그래프)

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from config import V_ORDER

def render(ana_df):
    """
    배송사별 분석 탭 렌더링
    Args:
        ana_df: 분석용 정상 완료 데이터
    """
    st.title("🚛 배송사별 비교 및 추이")
    
    # 1. 기초 데이터 준비
    total_compare = ana_df.groupby(['연월_키', '배송사_정제']).size().reset_index(name='완료건수').rename(columns={'배송사_정제': '지역센터'})
    all_months = sorted(total_compare['연월_키'].unique())
    total_len = len(all_months)
    
    if total_len > 0:
        if 'p_idx' not in st.session_state:
            st.session_state.p_idx = max(0, total_len - 3)
            
        # 2. 이동 버튼
        col_left, col_mid, col_right = st.columns([1, 3, 1])
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
        
        # 3. 절대 눕지 않는 막대 그래프
        fig_bar = go.Figure()
        
        # 사용할 지역센터 필터링 (V_ORDER 순서 유지)
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
                x=[[f"<b>{m}</b><br><span style='color:red;'>[총 합계: {monthly_totals[m]}건]</span>" for m in view_months], [center for _ in view_months]],
                y=y_vals,
                text=texts,
                textposition='outside',
                marker_color=colors[i % len(colors)],
                textfont=dict(size=14, family="Malgun Gothic")
            ))
            
        fig_bar.update_layout(
            barmode='group',
            margin=dict(t=80, b=150),
            xaxis=dict(title="", tickfont=dict(size=14, family="Malgun Gothic")),
            yaxis_title="완료건수",
            legend=dict(orientation="h", yanchor="bottom", y=1.1, xanchor="right", x=1),
            font=dict(family="Malgun Gothic")
        )
        st.plotly_chart(fig_bar, use_container_width=True, key="paged_bar_chart_final")
        
    else:
        st.warning("데이터가 없습니다.")
        
    st.divider()
    
    # 🎯 상세 분석 배송사 선택
    if ana_df.empty:
        return

    sel_v = st.selectbox("🎯 상세 분석 배송사 선택", [v for v in V_ORDER if v in ana_df['배송사_정제'].unique()])
    
    # 데이터 준비
    total_monthly = ana_df.groupby('연월_키').size().reset_index(name='전체건수')
    v_monthly = ana_df[ana_df['배송사_정제'] == sel_v].groupby('연월_키').size().reset_index(name='지역건수')
    df_combined = pd.merge(total_monthly, v_monthly, on='연월_키', how='left').fillna(0)
    
    # 이중 축 그래프
    fig_dual = make_subplots(specs=[[{"secondary_y": True}]])
    
    # 전체 건수 (막대)
    fig_dual.add_trace(
        go.Bar(
            x=df_combined['연월_키'],
            y=df_combined['전체건수'],
            name="전체 출고건수",
            marker_color='rgba(180, 180, 180, 0.5)',
            text=df_combined['전체건수'],
            textposition='inside',
            insidetextanchor='end',
            textfont=dict(size=11, color='white', family="Malgun Gothic"),
            hovertemplate="전체: %{y}건"
        ),
        secondary_y=False,
    )
    
    # 선택 지역 (선)
    fig_dual.add_trace(
        go.Scatter(
            x=df_combined['연월_키'],
            y=df_combined['지역건수'],
            name=f"{sel_v} 건수",
            mode='lines+markers+text',
            line=dict(color='#0077b6', width=3),
            marker=dict(size=10, symbol='circle'),
            text=df_combined['지역건수'].astype(int),
            textposition="top center",
            textfont=dict(size=14, color='#0077b6'),
            hovertemplate=f"{sel_v}: %{{y}}건"
        ),
        secondary_y=True,
    )
    
    max_total = df_combined['전체건수'].max() if not df_combined.empty else 100
    
    fig_dual.update_layout(
        title=dict(text=f"<b>📊 {sel_v} 지역 vs 전체 출고 추이 비교</b>", font=dict(size=20)),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=100, b=20),
        height=500,
        font=dict(family="Malgun Gothic")
    )
    
    fig_dual.update_xaxes(tickformat="%y년 %m월", dtick="M1", title_text="출고 연월")
    fig_dual.update_yaxes(title_text="전체 물량 (막대)", secondary_y=False, showgrid=False, range=[0, max_total * 1.3])
    fig_dual.update_yaxes(title_text=f"{sel_v} 물량 (선)", secondary_y=True, showgrid=True, range=[0, 3000])
    
    st.plotly_chart(fig_dual, use_container_width=True, key="dual_axis_chart")
