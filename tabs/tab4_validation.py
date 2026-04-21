# tabs/tab4_validation.py
# 4. 예측 모델 검증 (골든 데이 분석)

import streamlit as st
import pandas as pd
import datetime
import plotly.express as px
from config import V_ORDER
from services.prediction_ops import simulate_month_prediction, build_historical_day_trend, build_master_golden_summary


def _auto_working_day_for_month(month_key: str, today_kst: datetime.date) -> int:
    """
    선택 월 기준으로 '조회일(today_kst)의 일자'에 해당하는 영업일차를 계산한다.
    예) 오늘이 22일이면, 선택 월의 22일까지 영업일 수를 기준일로 사용.
    """
    y, m = map(int, str(month_key).split("-"))
    month_start = datetime.date(y, m, 1)
    if m == 12:
        month_end = datetime.date(y, 12, 31)
    else:
        month_end = datetime.date(y, m + 1, 1) - datetime.timedelta(days=1)

    day_in_month = min(today_kst.day, month_end.day)
    ref_date = datetime.date(y, m, day_in_month)
    # 탭4 기준일은 월~토(일요일 제외) 기준으로 계산한다.
    days = pd.date_range(month_start, ref_date)
    auto_day = int(len([d for d in days if d.weekday() != 6]))
    return max(1, min(24, auto_day))

def render(ana_df, ctx, cache_key=None):
    st.title("🔍 예측 모델 검증 및 골든 데이 분석")
    st.markdown("전월 데이터를 바탕으로 **'몇 영업일째의 예측이 가장 정확했는지'**를 분석하여 모델의 신뢰도를 검증합니다.")
    
    # 1. 상단 컨트롤러
    c1, c2, c3 = st.columns([1.5, 1, 2])
    available_months = sorted(ana_df['연월_키'].unique(), reverse=True)
    default_idx = 1 if len(available_months) > 1 else 0
    
    with c1:
        sel_month_key = st.selectbox("📅 검증 대상 월 선택", available_months, index=default_idx, key="v_month_sel")
    # 시뮬레이션 기준일을 '조회하는 날' 기준 영업일차로 자동 반영
    today_kst = ctx.get("today", datetime.date.today())
    auto_day_num = _auto_working_day_for_month(str(sel_month_key), today_kst)
    st.session_state["v_day_num"] = int(auto_day_num)

    with c2:
        sel_day_num = st.number_input(
            "📅 시뮬레이션 기준일 (영업일)",
            min_value=1,
            max_value=24,
            value=int(auto_day_num),
            key="v_day_num",
        )
    with c3:
        st.info(f"💡 **분석 시나리오:** {sel_month_key}월의 **{sel_day_num}영업일차** 시점 예측치 분석")
        
    # 2. 핵심 시뮬레이션 계산
    sim_state_key = f"tab4_sim::{cache_key}::{sel_month_key}::{int(sel_day_num)}"
    if sim_state_key not in st.session_state:
        st.session_state[sim_state_key] = simulate_month_prediction(ana_df, sel_month_key, int(sel_day_num), V_ORDER)
    test_df, sim_meta, df_hist = st.session_state[sim_state_key]
    target_date = sim_meta.get("target_date")
    sum_actual = sim_meta.get("sum_actual", 0)

    if target_date:
        st.subheader(f"📍 {sel_day_num}영업일차({target_date.strftime('%m/%d')}) 예측 결과")
        st.table(test_df.set_index('지역센터'))
        st.divider()
        
        # 4. 골든 데이 분석
        st.subheader(f"🏆 {sel_month_key} 예측 골든 데이 분석 (1~24 영업일)")
        
        best_acc = -1
        best_day_info = {}
        target_accuracy = 95.0
        fastest_golden_day = None
        for _, row_hist in df_hist.iterrows():
            d_acc = float(row_hist["정확도"])
            day_num = int(str(row_hist["영업일"]).replace("일차", ""))
            if d_acc >= target_accuracy and fastest_golden_day is None:
                fastest_golden_day = {"day": day_num, "date": row_hist["날짜"], "acc": d_acc}
            if d_acc > best_acc:
                best_acc = d_acc
                best_day_info = {"day": day_num, "date": row_hist["날짜"], "acc": d_acc}
                
        display_day = fastest_golden_day if fastest_golden_day else best_day_info
        
        if best_day_info:
            m1, m2 = st.columns([1, 2])
            with m1:
                st.metric("최적 예측 시점 (빠른달성)", f"{display_day['day']}영업일", f"{display_day['date']}")
                st.metric("해당 시점 정확도", f"{display_day['acc']:.1f}%")
                if fastest_golden_day:
                    st.caption(f"✅ 정확도 {target_accuracy}%를 달성한 최초의 날입니다.")
            with m2:
                fig_hist = px.bar(
                    df_hist, x='영업일', y='정확도', 
                    text=df_hist['정확도'].apply(lambda x: f"{x:.1f}%"), 
                    title=f"{sel_month_key} 영업일별 정확도 추이", 
                    color='정확도', color_continuous_scale='Blues'
                )
                fig_hist.add_hline(y=target_accuracy, line_dash="dash", line_color="red")
                fig_hist.update_layout(yaxis_range=[min(df_hist['정확도'])-5, 100], showlegend=False)
                st.plotly_chart(fig_hist, use_container_width=True)
                
        st.divider()
        
        # --- 역대 일차별 상세 분석 ---
        st.subheader(f"📊 3. 역대 {sel_day_num}영업일차 상세 정확도 추이")
        st.markdown(f"매월 **{sel_day_num}영업일차** 시점의 정확도를 분석합니다. (25년 5월 ~ 전월까지)")
        
        current_month_key = datetime.date.today().strftime('%Y-%m')
        daily_state_key = f"tab4_daytrend::{cache_key}::{int(sel_day_num)}::{current_month_key}"
        if daily_state_key not in st.session_state:
            st.session_state[daily_state_key] = build_historical_day_trend(
                ana_df, int(sel_day_num), month_from="2025-05", month_to_exclusive=current_month_key
            )
        df_daily = st.session_state[daily_state_key]
        if not df_daily.empty:
            c_l, c_r = st.columns([1, 2])
            with c_l:
                st.dataframe(df_daily.set_index("연월"), height=300, use_container_width=True)
            with c_r:
                fig_daily = px.line(df_daily, x="연월", y="정확도(%)", markers=True, title=f"📅 역대 {sel_day_num}일차 정확도 추이", text="정확도(%)")
                fig_daily.update_xaxes(tickformat="%y년 %m월", dtick="M1", tickangle=0)
                fig_daily.update_traces(textposition="top center")
                fig_daily.update_layout(yaxis_range=[85, 105], margin=dict(l=20, r=20, t=50, b=20))
                st.plotly_chart(fig_daily, use_container_width=True)
                
            st.info(f"💡 {sel_day_num}일차 역대 평균 정확도: **{df_daily['정확도(%)'].mean():.1f}%**")
            
        st.divider()
        
        # --- 역대 통합 골든 데이 분석 ---
        st.subheader("🌐 역대 통합 골든 데이 분석 (25년 5월~전월)")
        st.markdown("전체 기간을 분석하여 **최고 정확도 수준에 가장 먼저 도달하는 가성비 시점**을 도출합니다.")
        master_state_key = f"tab4_master::{cache_key}::{current_month_key}"
        if master_state_key not in st.session_state:
            st.session_state[master_state_key] = build_master_golden_summary(
                ana_df, month_from="2025-05", month_to_exclusive=current_month_key, max_day=24
            )
        df_master, master_meta = st.session_state[master_state_key]
        target_months = master_meta.get("target_months", [])
        if len(target_months) > 0:
            if not df_master.empty:
                max_acc = df_master['평균정확도'].max()
                tolerance = 3.0
                candidate_days = df_master[df_master['평균정확도'] >= (max_acc - tolerance)]
                m_golden = candidate_days.sort_values(by='영업일', ascending=True).iloc[0]
                
                mm1, mm2 = st.columns([1, 2])
                with mm1:
                    st.metric("🏆 마스터 골든 데이", f"{int(m_golden['영업일'])}영업일차")
                    st.metric("📈 기대 정확도", f"{m_golden['평균정확도']:.1f}%")
                    st.caption(f"📅 분석 범위: {target_months[0]} ~ {target_months[-1]}")
                    st.info(f"💡 월말 최고 정확도({max_acc:.1f}%) 대비 차이가 {tolerance}% 이내인 가장 빠른 시점을 도출했습니다.")
                with mm2:
                    fig_master = px.line(df_master, x='영업일', y='평균정확도', markers=True, title="역대 영업일별 평균 정확도 추이")
                    fig_master.add_vline(x=m_golden['영업일'], line_dash="dash", line_color="green")
                    fig_master.add_annotation(x=m_golden['영업일'], y=m_golden['평균정확도'], text="Golden Day", showarrow=True, arrowhead=1)
                    fig_master.update_layout(yaxis_range=[85, 105])
                    st.plotly_chart(fig_master, use_container_width=True)
            else:
                st.warning("분석 가능한 데이터 범위가 부족합니다.")
