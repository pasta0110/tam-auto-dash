# tabs/tab3_prediction.py
# 3. 당월 출고 예측

import streamlit as st
import pandas as pd
from config import V_ORDER
from services.prediction_ops import build_tab3_prediction

def render(ana_df, ctx, cache_key=None, delivery_df=None):
    """
    당월 출고 예측 탭 렌더링
    """
    st.title("🚀 당월 출고 예측 (최근 30일 페이스 + 역대 정확도 보정)")
    mobile_mode = bool(st.session_state.get("ui_mobile_mode", str(st.query_params.get("mobile", "0")) == "1"))
    
    yesterday_str = ctx['yesterday_str']
    state_key = f"tab3_prediction::{cache_key}::{ctx.get('m_key')}::{ctx.get('yesterday_str')}"
    if state_key not in st.session_state:
        st.session_state[state_key] = build_tab3_prediction(ana_df, ctx, V_ORDER, delivery_df=delivery_df)
    pred_rows, meta = st.session_state[state_key]
    hist_acc = meta.get("historical_accuracy")
    q_day = meta.get("query_working_day_num")
    hist_months = meta.get("historical_months", 0)
    if meta.get("month_end_mode"):
        acc_text = f"{hist_acc:.1f}%, {hist_months}개월" if hist_acc else "데이터 부족"
        st.info(
            f"💡 말일 특수 기준입니다. 배송예정일이 오늘인 물량에서 오늘 완료분을 제외해 남은 물량을 계산합니다. "
            f"역대 {q_day}영업일차 평균 정확도({acc_text})는 '최종 예측' 보정에 반영합니다."
        )
    elif hist_acc:
        st.info(
            f"💡 최근 30일 영업일 {meta['recent_working_days']}일의 실적을 반영해 '당월 예측'을 계산하고, "
            f"역대 {q_day}영업일차 평균 정확도({hist_acc:.1f}%, {hist_months}개월)로 '최종 예측'을 보정합니다."
        )
    else:
        st.info(
            f"💡 최근 30일 영업일 {meta['recent_working_days']}일의 실적을 반영하여 남은 {meta['remain_w']}일간의 물량을 예측합니다. "
            f"(역대 정확도 데이터 부족으로 보정 미적용)"
        )
    
    st.subheader("📍 지역별 출고 예측")
    pred_df = pd.DataFrame(pred_rows).set_index('배송사')
    hist_acc = meta.get("historical_accuracy")
    if hist_acc:
        pred_df = pred_df.rename(
            columns={
                "당월 예측": f"당월 예측 (정확도 {hist_acc:.1f}%)",
                "최종 예측": "최종 예측 (정확도 100%)",
            }
        )
    else:
        pred_df = pred_df.rename(
            columns={
                "당월 예측": "당월 예측 (정확도 -)",
                "최종 예측": "최종 예측 (정확도 100%)",
            }
        )

    if mobile_mode:
        keep_cols = [c for c in pred_df.columns if c.startswith("현재 실적(당월)") or c.startswith("당월 예측") or c.startswith("최종 예측")]
        if keep_cols:
            pred_df = pred_df[keep_cols]
        st.dataframe(pred_df, use_container_width=True, height=360)
    else:
        st.table(pred_df)
    st.caption(f"최종 업데이트: {yesterday_str} | 영업일 기준: 월~토(공휴일 제외) | 배송상태 '완료' 집계")
