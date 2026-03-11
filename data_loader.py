# data_loader.py
# 데이터 로드 및 전처리

import os
import streamlit as st
import pandas as pd
import requests
from io import BytesIO
from config import (
    DATA_URL,
    ORDER_CSV_PATH,
    DELIVERY_CSV_PATH,
    ORDER_CSV_URL,
    DELIVERY_CSV_URL,
)

@st.cache_data(ttl=300)
def load_raw_data():
    """
    로컬 CSV 우선 로드, 없으면 원격 CSV 로드 (캐싱 적용: 5분)
    (레거시) 둘 다 실패하면 원격 엑셀(DATA_URL)로 시도
    """
    try:
        ord_df = None
        del_df = None

        try:
            if os.path.exists(ORDER_CSV_PATH):
                ord_df = pd.read_csv(ORDER_CSV_PATH, encoding="utf-8-sig", low_memory=False)
            else:
                resp = requests.get(ORDER_CSV_URL, timeout=20)
                resp.raise_for_status()
                ord_df = pd.read_csv(BytesIO(resp.content), encoding="utf-8-sig", low_memory=False)
        except Exception:
            ord_df = None

        try:
            if os.path.exists(DELIVERY_CSV_PATH):
                del_df = pd.read_csv(DELIVERY_CSV_PATH, encoding="utf-8-sig", low_memory=False)
            else:
                resp = requests.get(DELIVERY_CSV_URL, timeout=20)
                resp.raise_for_status()
                del_df = pd.read_csv(BytesIO(resp.content), encoding="utf-8-sig", low_memory=False)
        except Exception:
            del_df = None

        if ord_df is None or del_df is None:
            response = requests.get(DATA_URL, timeout=20)
            response.raise_for_status()
            with BytesIO(response.content) as f:
                ord_df = pd.read_excel(f, sheet_name="주문건")
                f.seek(0)
                del_df = pd.read_excel(f, sheet_name="출고건", skiprows=13)
             
        # 컬럼명 공백 제거
        ord_df.columns = [str(c).strip() for c in ord_df.columns]
        del_df.columns = [str(c).strip() for c in del_df.columns]
        
        return ord_df, del_df
    
    except Exception as e:
        st.error(f"⚠️ 데이터 로딩 실패: {e}")
        return None, None
