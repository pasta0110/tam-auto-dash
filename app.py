import streamlit as st
import datetime

from data_loader import load_data
from data_processor import process_data
from utils.date_utils import get_w_days

from tabs.tab1_summary import render_summary
from tabs.tab2_delivery import render_delivery
from tabs.tab3_prediction import render_prediction
from tabs.tab4_validation import render_validation


st.set_page_config(
    page_title="청호나이스 현황판",
    layout="wide",
    page_icon="📊"
)

# 데이터 로드
order_df, delivery_df = load_data()

# ana_df로 사용
ana_df = delivery_df
st.write(ana_df.columns)

# 날짜 변수 생성
yesterday = datetime.date.today() - datetime.timedelta(days=1)
yesterday_str = yesterday.strftime("%Y-%m-%d")
m_key = yesterday.strftime("%Y-%m")


# 탭 생성
tab1, tab2, tab3, tab4 = st.tabs([
    "📋 1. 종합 현황",
    "📈 2. 배송사별 분석",
    "🚀 3. 당월 출고 예측",
    "🔍 4. 예측 모델 검증"
])


with tab1:
    render_summary(order_df, delivery_df)

with tab2:
    render_delivery(ana_df)

with tab3:
    render_prediction(ana_df, yesterday, yesterday_str, m_key)

with tab4:
    render_validation(ana_df)