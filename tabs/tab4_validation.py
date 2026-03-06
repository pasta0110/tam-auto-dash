# tabs/tab4_validation.py
# 4. 예측 모델 검증 (골든 데이 분석)

import streamlit as st
import pandas as pd
import datetime
import plotly.express as px
from datetime import timedelta
from utils.date_utils import get_w_days
from config import V_ORDER

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
        
    # 2. 날짜 및 기초 데이터 설정
    sel_year, sel_month = map(int, sel_month_key.split('-'))
    sim_m_start = datetime.date(sel_year, sel_month, 1)
    
    if sel_month == 12:
        sim_m_end = datetime.date(sel_year, 12, 31)
    else:
        sim_m_end = datetime.date(sel_year, sel_month + 1, 1) - timedelta(days=1)
        
    s_total_w = get_w_days(sim_m_start, sim_m_end)
    s_real_final = ana_df[ana_df['연월_키'] == sel_month_key]
    sum_actual = len(s_real_final)
    
    # 3. 선택한 영업일 날짜 찾기
    month_days = pd.date_range(sim_m_start, sim_m_end)
    target_date = None
    w_count = 0
    
    for d in month_days:
        if get_w_days(d.date(), d.date()) > 0:
            w_count += 1
            if w_count == sel_day_num:
                target_date = d.date()
                break
                
    if target_date:
        s_act_data = ana_df[(ana_df['배송예정일_DT'].dt.date >= sim_m_start) & (ana_df['배송예정일_DT'].dt.date <= target_date)]
        s_30_start = target_date - timedelta(days=30)
        s_recent_30d = ana_df[(ana_df['배송예정일_DT'].dt.date >= s_30_start) & (ana_df['배송예정일_DT'].dt.date <= target_date)]
        
        s_recent_w = get_w_days(s_30_start, target_date)
        s_remain_w = s_total_w - sel_day_num
        
        test_rows = []
        sum_curr, sum_recent_cnt, sum_pred_rem, sum_final_pred = 0, 0, 0, 0
        
        for v in V_ORDER:
            if v in ana_df['배송사_정제'].unique():
                v_curr = len(s_act_data[s_act_data['배송사_정제'] == v])
                v_recent = len(s_recent_30d[s_recent_30d['배송사_정제'] == v])
                
                v_pace = v_recent / s_recent_w if s_recent_w > 0 else 0
                v_rem_pred = int(v_pace * s_remain_w)
                v_final_pred = v_curr + v_rem_pred
                v_actual = len(s_real_final[s_real_final['배송사_정제'] == v])
                
                v_acc = (1 - abs((v_actual - v_final_pred)/v_actual)) * 100 if v_actual > 0 else 0
                
                sum_curr += v_curr
                sum_recent_cnt += v_recent
                sum_pred_rem += v_rem_pred
                sum_final_pred += v_final_pred
                
                test_rows.append({
                    '지역센터': v,
                    '당시 실적': f"{v_curr}건",
                    '일평균 페이스': f"{v_pace:.1f}건/일",
                    '예측 최종': f"{v_final_pred}건",
                    '실제 결과': f"{v_actual}건",
                    '정확도': f"{v_acc:.1f}%"
                })
                
        total_acc = (1 - abs((sum_actual - sum_final_pred)/sum_actual)) * 100 if sum_actual > 0 else 0
        
        test_rows.append({
            '지역센터': '📌 합계',
            '당시 실적': f"{sum_curr}건",
            '일평균 페이스': '-',
            '예측 최종': f"{sum_final_pred}건",
            '실제 결과': f"{sum_actual}건",
            '정확도': f"{total_acc:.1f}%"
        })
        
        st.subheader(f"📍 {sel_day_num}영업일차({target_date.strftime('%m/%d')}) 예측 결과")
        st.table(pd.DataFrame(test_rows).set_index('지역센터'))
        st.divider()
        
        # 4. 골든 데이 분석
        st.subheader(f"🏆 {sel_month_key} 예측 골든 데이 분석 (1~24 영업일)")
        
        acc_history = []
        best_acc = -1
        best_day_info = {}
        target_accuracy = 95.0
        fastest_golden_day = None
        
        temp_w_count = 0
        
        for d in month_days:
            if get_w_days(d.date(), d.date()) == 0: continue
            temp_w_count += 1
            if temp_w_count > 24: break
            
            d_date = d.date()
            d_act = len(ana_df[(ana_df['연월_키'] == sel_month_key) & (ana_df['배송예정일_DT'].dt.date <= d_date)])
            
            d_30_s = d_date - timedelta(days=30)
            d_30_data = ana_df[(ana_df['배송예정일_DT'].dt.date >= d_30_s) & (ana_df['배송예정일_DT'].dt.date <= d_date)]
            d_30_w = get_w_days(d_30_s, d_date)
            
            d_pace = len(d_30_data) / d_30_w if d_30_w > 0 else 0
            d_pred = d_act + int(d_pace * (s_total_w - temp_w_count))
            d_acc = (1 - abs((sum_actual - d_pred)/sum_actual)) * 100 if sum_actual > 0 else 0
            
            acc_history.append({"영업일": f"{temp_w_count}일차", "날짜": d_date.strftime('%m/%d'), "정확도": d_acc})
            
            if d_acc >= target_accuracy and fastest_golden_day is None:
                fastest_golden_day = {"day": temp_w_count, "date": d_date.strftime('%m/%d'), "acc": d_acc}
            
            if d_acc > best_acc:
                best_acc = d_acc
                best_day_info = {"day": temp_w_count, "date": d_date.strftime('%m/%d'), "acc": d_acc}
                
        display_day = fastest_golden_day if fastest_golden_day else best_day_info
        
        if best_day_info:
            m1, m2 = st.columns([1, 2])
            with m1:
                st.metric("최적 예측 시점 (빠른달성)", f"{display_day['day']}영업일", f"{display_day['date']}")
                st.metric("해당 시점 정확도", f"{display_day['acc']:.1f}%")
                if fastest_golden_day:
                    st.caption(f"✅ 정확도 {target_accuracy}%를 달성한 최초의 날입니다.")
            with m2:
                df_hist = pd.DataFrame(acc_history)
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
