# app.py
# 메인 실행 파일 (진입점)

import streamlit as st
import config
from utils.date_utils import get_current_context
from data_loader import load_raw_data
from data_processor import process_data

# 탭 모듈 임포트 (각 기능을 담당)
from tabs import tab1_summary, tab1_5_insights, tab2_delivery, tab3_prediction, tab4_validation, tab5_map

# 1. 페이지 기본 설정 (가장 먼저 실행되어야 함)
st.set_page_config(
    page_title=config.APP_TITLE,
    layout="wide",
    page_icon=config.APP_ICON
)

# 2. 전역 스타일 적용 (CSS)
st.markdown(config.CSS_STYLE, unsafe_allow_html=True)

# 3. 데이터 로드 및 전처리
# (캐싱은 data_loader 내부에서 처리됨)
raw_order_df, raw_delivery_df = load_raw_data()

# 4. 날짜 컨텍스트 확보 (오늘, 어제, 이번 달 등)
ctx = get_current_context()

if raw_order_df is not None and raw_delivery_df is not None:
    # 데이터 가공 (컬럼 추가, 필터링 등)
    order_df, delivery_df, ana_df = process_data(raw_order_df, raw_delivery_df)
    
    # 5. 메인 UI 구성 (탭)
    tab1, tab1_5, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 1. 종합 현황", 
        "📌 1.5 인사이트",
        "📈 2. 배송사별 분석", 
        "🚀 3. 당월 출고 예측", 
        "🔍 4. 예측 모델 검증", 
        "📍 5. 배송 지도"
    ])
    
    # 각 탭에 필요한 데이터 전달 및 렌더링
    with tab1:
        tab1_summary.render(order_df, delivery_df, ana_df, ctx)

    with tab1_5:
        tab1_5_insights.render(order_df, delivery_df, ctx)
        
    with tab2:
        tab2_delivery.render(ana_df)
        
    with tab3:
        tab3_prediction.render(ana_df, ctx)
        
    with tab4:
        tab4_validation.render(ana_df, ctx)
        
    with tab5:
        tab5_map.render(ana_df)

else:
    st.error("데이터를 불러올 수 없습니다. 네트워크 상태를 확인해주세요.")
