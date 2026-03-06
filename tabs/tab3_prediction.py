import streamlit as st
import pandas as pd
import datetime
from config import V_ORDER
from utils.date_utils import get_w_days

def render_prediction(ana_df, yesterday, yesterday_str, m_key):

    st.title("🚀 당월 출고 최종 예측 (최근 30일 페이스)")

    m_start = yesterday.replace(day=1)
    m_end = (m_start + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)

    total_w = get_w_days(m_start, m_end)
    passed_w = get_w_days(m_start, yesterday)
    remain_w = total_w - passed_w

    last_30_days_start = yesterday - datetime.timedelta(days=30)

    recent_30d_data = ana_df[
        (ana_df['배송예정일_DT'] >= pd.to_datetime(last_30_days_start)) &
        (ana_df['배송예정일_DT'] <= pd.to_datetime(yesterday))
    ]

    recent_working_days = get_w_days(last_30_days_start, yesterday)

    st.info(f"💡 최근 30일 영업일 {recent_working_days}일의 실적을 반영하여 남은 {remain_w}일간의 물량을 예측합니다.")

    sum_curr, sum_avg, sum_remain, sum_total = 0, 0.0, 0, 0
    pred_rows = []

    for v in V_ORDER:

        if v in ana_df['배송사_정제'].unique():

            curr_act = len(
                ana_df[
                    (ana_df['배송사_정제'] == v) &
                    (ana_df['연월_키'] == m_key)
                ]
            )

            v_recent_count = len(recent_30d_data[recent_30d_data['배송사_정제'] == v])

            avg_30d = v_recent_count / recent_working_days if recent_working_days > 0 else 0

            rem_pred = int(avg_30d * remain_w)

            projected = curr_act + rem_pred

            sum_curr += curr_act
            sum_avg += avg_30d
            sum_remain += rem_pred
            sum_total += projected

            pred_rows.append({
                '배송사': v,
                '현재 실적(당월)': f"{curr_act} 건",
                '최근 30일 평균': f"{avg_30d:.1f} 건/일",
                f'남은 영업일 예상({remain_w}일)': f"{rem_pred} 건",
                '당월 최종 예측': f"{projected} 건"
            })

    pred_rows.append({
        '배송사': '📌 합계',
        '현재 실적(당월)': f"{sum_curr} 건",
        '최근 30일 평균': f"{sum_avg:.1f} 건/일",
        f'남은 영업일 예상({remain_w}일)': f"{sum_remain} 건",
        '당월 최종 예측': f"{sum_total} 건"
    })

    st.subheader("📍 지역별 출고 예측")

    st.table(pd.DataFrame(pred_rows).set_index('배송사'))

    st.caption(f"최종 업데이트: {yesterday_str} | 영업일 기준: 월~토(공휴일 제외) | 배송상태 '완료' 집계")