# data_loader.py
# 데이터 로드 및 전처리

import streamlit as st
import pandas as pd
import requests
from io import BytesIO
from config import DATA_URL

@st.cache_data(ttl=300)
def load_raw_data():
    """
    GitHub 또는 외부 URL에서 엑셀 데이터를 로드 (캐싱 적용: 5분)
    """
    try:
        response = requests.get(DATA_URL, timeout=15)
        response.raise_for_status()
        
        with BytesIO(response.content) as f:
            # 1. 주문 데이터 (첫 번째 시트)
            ord_df = pd.read_excel(f, sheet_name='주문건')
            f.seek(0)
            # 2. 출고 데이터 (두 번째 시트, skiprows=13)
            del_df = pd.read_excel(f, sheet_name='출고건', skiprows=13)
            
        # 컬럼명 공백 제거
        ord_df.columns = [str(c).strip() for c in ord_df.columns]
        del_df.columns = [str(c).strip() for c in del_df.columns]
        
        return ord_df, del_df
    
    except Exception as e:
        st.error(f"⚠️ 데이터 로딩 실패: {e}")
        return None, None
