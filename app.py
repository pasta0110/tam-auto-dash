import streamlit as st

from data_loader import load_data

from tabs.tab1_summary import render_tab1
from tabs.tab2_delivery import render_delivery
from tabs.tab3_prediction import render_tab3
from tabs.tab4_validation import render_tab4
from tabs.tab5_map import render_tab5

st.set_page_config(
    page_title="청호나이스 현황판",
    layout="wide",
    page_icon="📊"
)

order_df, delivery_df = load_data()

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📋 1. 종합 현황",
    "📈 2. 배송사별 분석",
    "🚀 3. 당월 출고 예측",
    "🔍 4. 예측 모델 검증",
    "📍 5. 배송 지도"
])

with tab1:
    render_tab1(order_df, delivery_df)

with tab2:
    render_delivery(ana_df)

with tab3:
    render_tab3(order_df, delivery_df)

with tab4:
    render_tab4(order_df, delivery_df)

with tab5:
    render_tab5(order_df, delivery_df)