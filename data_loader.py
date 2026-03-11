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

def _format_dt_kst(dt):
    try:
        from zoneinfo import ZoneInfo
        import datetime

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")
    except Exception:
        return str(dt)


def _http_last_modified(url: str):
    try:
        r = requests.head(url, timeout=10, allow_redirects=True)
        lm = r.headers.get("Last-Modified")
        etag = r.headers.get("ETag")
        return {"last_modified": lm, "etag": etag}
    except Exception:
        return {"last_modified": None, "etag": None}


@st.cache_data(ttl=60)
def get_data_snapshot_info():
    """
    UI용: 현재 앱이 보고 있는 CSV의 스냅샷 정보를 반환합니다.
    - 로컬 파일이 있으면 로컬 mtime
    - 아니면 GitHub raw의 Last-Modified 헤더(있으면)
    """
    info = {}

    if os.path.exists(ORDER_CSV_PATH):
        info["order_source"] = "local"
        info["order_path_or_url"] = ORDER_CSV_PATH
        try:
            import datetime

            dt = datetime.datetime.fromtimestamp(os.path.getmtime(ORDER_CSV_PATH))
            info["order_mtime_kst"] = _format_dt_kst(dt)
        except Exception:
            info["order_mtime_kst"] = None
    else:
        info["order_source"] = "remote"
        info["order_path_or_url"] = ORDER_CSV_URL
        meta = _http_last_modified(ORDER_CSV_URL)
        info["order_last_modified"] = meta["last_modified"]
        info["order_etag"] = meta["etag"]

    if os.path.exists(DELIVERY_CSV_PATH):
        info["delivery_source"] = "local"
        info["delivery_path_or_url"] = DELIVERY_CSV_PATH
        try:
            import datetime

            dt = datetime.datetime.fromtimestamp(os.path.getmtime(DELIVERY_CSV_PATH))
            info["delivery_mtime_kst"] = _format_dt_kst(dt)
        except Exception:
            info["delivery_mtime_kst"] = None
    else:
        info["delivery_source"] = "remote"
        info["delivery_path_or_url"] = DELIVERY_CSV_URL
        meta = _http_last_modified(DELIVERY_CSV_URL)
        info["delivery_last_modified"] = meta["last_modified"]
        info["delivery_etag"] = meta["etag"]

    return info


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
