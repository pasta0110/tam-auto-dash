# tabs/tab3_prediction.py
# 3. 당월 출고 예측

import streamlit as st
import pandas as pd
from config import V_ORDER
from services.prediction_ops import build_tab3_prediction

def render(ana_df, ctx, cache_key=None):
    """
    당월 출고 예측 탭 렌더링
    """
    st.title("🚀 당월 출고 최종 예측 (최근 30일 페이스)")
    mobile_mode = str(st.query_params.get("mobile", "0")) == "1"
    
    yesterday_str = ctx['yesterday_str']
    state_key = f"tab3_prediction::{cache_key}::{ctx.get('m_key')}::{ctx.get('yesterday_str')}"
    if state_key not in st.session_state:
        st.session_state[state_key] = build_tab3_prediction(ana_df, ctx, V_ORDER)
    pred_rows, meta = st.session_state[state_key]
    st.info(f"💡 최근 30일 영업일 {meta['recent_working_days']}일의 실적을 반영하여 남은 {meta['remain_w']}일간의 물량을 예측합니다.")
    
    st.subheader("📍 지역별 출고 예측")
    pred_df = pd.DataFrame(pred_rows).set_index('배송사')
    if mobile_mode:
        keep_cols = [c for c in ["현재 실적(당월)", "당월 최종 예측"] if c in pred_df.columns]
        if keep_cols:
            pred_df = pred_df[keep_cols]
        st.dataframe(pred_df, use_container_width=True, height=360)
    else:
        st.table(pred_df)
    st.caption(f"최종 업데이트: {yesterday_str} | 영업일 기준: 월~토(공휴일 제외) | 배송상태 '완료' 집계")
