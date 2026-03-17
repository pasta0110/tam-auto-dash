# tabs/tab4_validation.py
# 4. 예측 모델 검증 (골든 데이 분석)

import streamlit as st
import pandas as pd
import datetime
import plotly.express as px
from datetime import timedelta
from utils.date_utils import get_w_days
from config import V_ORDER
from services.prediction_ops import simulate_month_prediction

def render(ana_df, ctx):
    st.title("🔍 예측 모델 검증 및 골든 데이 분석")
    st.markdown("전월 데이터를 바탕으로 **'몇 영업일째의 예측이 가장 정확했는지'**를 분석하여 모델의 신뢰도를 검증합니다.")
    
    # 1. 상단 컨트롤러
    c1, c2, c3 = st.columns([1.5, 1, 2])
    available_months = sorted(ana_df['연월_키'].unique(), reverse=True)
    default_idx = 1 if len(available_months) > 1 else 0
    
    with c1:
        sel_month_key = st.selectbox("📅 검증 대상 월 선택", available_months, index=default_idx, key="v_month_sel")
    with c2:
        sel_day_num = st.number_input("📅 시뮬레이션 기준일 (영업일)", min_value=1, max_value=20, value=3, key="v_day_num")
    with c3:
        st.info(f"💡 **분석 시나리오:** {sel_month_key}월의 **{sel_day_num}영업일차** 시점 예측치 분석")
        
    # 2. 핵심 시뮬레이션 계산
    test_df, sim_meta, df_hist = simulate_month_prediction(ana_df, sel_month_key, int(sel_day_num), V_ORDER)
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
        target_months = [m for m in sorted(ana_df['연월_키'].unique()) if "2025-05" <= m < current_month_key]
        
        daily_trend_data = []
        
        for m_key in target_months:
            m_real_df = ana_df[ana_df['연월_키'] == m_key]
            m_final_act = len(m_real_df)
            if m_final_act == 0: continue
            
            m_y, m_m = map(int, m_key.split('-'))
            m_s = datetime.date(m_y, m_m, 1)
            
            if m_m == 12:
                m_e = datetime.date(m_y, 12, 31)
            else:
                m_e = datetime.date(m_y, m_m + 1, 1) - timedelta(days=1)
                
            m_total_w = get_w_days(m_s, m_e)
            m_days = pd.date_range(m_s, m_e)
            
            t_dt, t_w = None, 0
            for d in m_days:
                if get_w_days(d.date(), d.date()) > 0:
                    t_w += 1
                    if t_w == sel_day_num:
                        t_dt = d.date()
                        break
                        
            if t_dt:
                d_act = len(m_real_df[m_real_df['배송예정일_DT'].dt.date <= t_dt])
                d_30_s = t_dt - timedelta(days=30)
                d_30_w = get_w_days(d_30_s, t_dt)
                d_30_cnt = len(ana_df[(ana_df['배송예정일_DT'].dt.date >= d_30_s) & (ana_df['배송예정일_DT'].dt.date <= t_dt)])
                
                d_pace = d_30_cnt / d_30_w if d_30_w > 0 else 0
                d_pred = d_act + int(d_pace * (m_total_w - sel_day_num))
                d_acc = max(0, min(100, (1 - abs((m_final_act - d_pred) / m_final_act)) * 100)) if m_final_act > 0 else 0
                
                daily_trend_data.append({
                    "연월": m_key, "실제결과": f"{m_final_act}건", "예측치": f"{d_pred}건", "정확도(%)": round(d_acc, 1)
                })
                
        if daily_trend_data:
            df_daily = pd.DataFrame(daily_trend_data)
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
        
        if len(target_months) > 0:
            master_summary = {}
            for m_key in target_months:
                m_real_final_df = ana_df[ana_df['연월_키'] == m_key]
                m_final_actual_cnt = len(m_real_final_df)
                
                m_year, m_month = map(int, m_key.split('-'))
                m_start = datetime.date(m_year, m_month, 1)
                if m_month == 12:
                    m_end = datetime.date(m_year, 12, 31)
                else:
                    m_end = datetime.date(m_year, m_month + 1, 1) - timedelta(days=1)
                    
                m_tot_w = get_w_days(m_start, m_end)
                
                tw = 0
                for d in pd.date_range(m_start, m_end):
                    if get_w_days(d.date(), d.date()) == 0: continue
                    tw += 1
                    if tw > 24: break
                    
                    d_dt = d.date()
                    d_act_cnt = len(m_real_final_df[m_real_final_df['배송예정일_DT'].dt.date <= d_dt])
                    d_30_s = d_dt - timedelta(days=30)
                    d_30_w = get_w_days(d_30_s, d_dt)
                    d_30_data_cnt = len(ana_df[(ana_df['배송예정일_DT'].dt.date >= d_30_s) & (ana_df['배송예정일_DT'].dt.date <= d_dt)])
                    
                    d_p = d_30_data_cnt / d_30_w if d_30_w > 0 else 0
                    d_pred = d_act_cnt + int(d_p * (m_tot_w - tw))
                    d_acc = max(0, min(100, (1 - abs((m_final_actual_cnt - d_pred) / m_final_actual_cnt)) * 100)) if m_final_actual_cnt > 0 else 0
                    
                    if tw not in master_summary:
                        master_summary[tw] = []
                    master_summary[tw].append(d_acc)
                    
            master_history = []
            for w, accs in master_summary.items():
                avg_a = sum(accs) / len(accs)
                master_history.append({"영업일": w, "평균정확도": avg_a})
                
            df_master = pd.DataFrame(master_history)
            
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
