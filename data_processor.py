# data_processor.py
# 데이터 가공 및 정제 로직

import pandas as pd
from utils.text_utils import clean_v, get_qty, get_main_cat, check_panel

def process_data(order_df, delivery_df):
    """
    로드된 데이터프레임을 전처리하여 분석용 데이터 생성
    Returns:
        order_df (가공됨), delivery_df (가공됨), ana_df (분석용 필터링됨)
    """
    
    # 1. 공통 전처리 (주문, 배송 데이터)
    for df in [order_df, delivery_df]:
        if df is None: continue
        # 수량, 품목구분, 판넬여부 컬럼 생성
        df['수량'] = df['상품명'].apply(get_qty)
        df['품목구분'] = df['상품명'].apply(get_main_cat)
        df['is_판넬01'] = df['상품명'].apply(lambda x: check_panel(x, "판넬01"))
        df['is_판넬05'] = df['상품명'].apply(lambda x: check_panel(x, "판넬05"))
    
    if delivery_df is not None:
        # 2. 배송 데이터 추가 정제
        delivery_df['배송사_정제'] = delivery_df['배송사'].apply(clean_v)
        delivery_df['배송예정일_DT'] = pd.to_datetime(delivery_df['배송예정일'], errors='coerce')
        
        # 유효한 날짜만 필터링 및 정렬
        delivery_df = delivery_df.dropna(subset=['배송예정일_DT']).sort_values('배송예정일_DT')
        delivery_df['연월_키'] = delivery_df['배송예정일_DT'].dt.strftime('%Y-%m')
        
        # 3. 분석용 데이터셋 (ana_df): '완료' 또는 '4' 상태이면서 '정상' 주문인 건
        #    배송상태 컬럼명 자동 탐지
        status_col = '배송상태' if '배송상태' in delivery_df.columns else 'delivery_stat_nm'
        
        ana_df = delivery_df[
            (delivery_df[status_col].astype(str).str.contains('완료|4', na=False)) & 
            (delivery_df['주문유형'].str.contains('정상', na=False))
        ].copy()
        
        return order_df, delivery_df, ana_df

    return order_df, delivery_df, None
