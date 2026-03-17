# data_processor.py
# 데이터 가공 및 정제 로직

import pandas as pd
import streamlit as st
from utils.text_utils import clean_v, get_qty, get_main_cat, check_panel
from services.domain_rules import filter_cheongho, delivery_event_flags

def _mode_or_first(series: pd.Series):
    s = series.dropna().astype(str)
    if s.empty:
        return None
    try:
        return s.mode().iloc[0]
    except Exception:
        return s.iloc[0]


def build_order_summary(order_df: pd.DataFrame, delivery_df: pd.DataFrame) -> pd.DataFrame:
    """
    주문번호 단위 요약 테이블 (Order KPI용 베이스)
    - 이벤트는 delivery_df(1:N)를 주문번호 단위로 집계합니다.
    - 취소 정의: 배송상태 == '미설치'
    - 우선순위 최종상태: 반품 > 교환 > AS > 취소 > 정상
    """
    if order_df is None or order_df.empty or "주문번호" not in order_df.columns:
        return pd.DataFrame()

    o = order_df.copy()
    d = delivery_df.copy() if delivery_df is not None else pd.DataFrame()

    o = filter_cheongho(o)
    d = filter_cheongho(d)

    base = (
        o.groupby("주문번호", dropna=False)
        .agg(
            주문유형=("주문유형", _mode_or_first) if "주문유형" in o.columns else ("주문번호", "size"),
            주문상태=("주문상태", _mode_or_first) if "주문상태" in o.columns else ("주문번호", "size"),
            등록일=("등록일", "min") if "등록일" in o.columns else ("주문번호", "size"),
            배송예정일=("배송예정일", "min") if "배송예정일" in o.columns else ("주문번호", "size"),
            판매인=("판매인", _mode_or_first) if "판매인" in o.columns else ("주문번호", "size"),
            판매지국=("판매지국", _mode_or_first) if "판매지국" in o.columns else ("주문번호", "size"),
            수취인=("수취인", _mode_or_first) if "수취인" in o.columns else ("주문번호", "size"),
        )
        .reset_index()
    )

    if d.empty or "주문번호" not in d.columns:
        for c in ["AS_이벤트수", "교환_이벤트수", "반품_이벤트수", "취소_이벤트수"]:
            base[c] = 0
    else:
        flags = delivery_event_flags(d)
        as_m = flags["is_as"]
        ex_m = flags["is_exchange"]
        ret_m = flags["is_return"]
        cancel_m = flags["is_cancel"]

        ev = (
            d.assign(_as=as_m.astype(int), _ex=ex_m.astype(int), _ret=ret_m.astype(int), _can=cancel_m.astype(int))
            .groupby("주문번호", dropna=False)[["_as", "_ex", "_ret", "_can"]]
            .sum()
            .rename(columns={"_as": "AS_이벤트수", "_ex": "교환_이벤트수", "_ret": "반품_이벤트수", "_can": "취소_이벤트수"})
            .reset_index()
        )
        base = base.merge(ev, on="주문번호", how="left").fillna(
            {"AS_이벤트수": 0, "교환_이벤트수": 0, "반품_이벤트수": 0, "취소_이벤트수": 0}
        )

    for c in ["AS_이벤트수", "교환_이벤트수", "반품_이벤트수", "취소_이벤트수"]:
        base[c] = base[c].astype(int)

    base["AS발생"] = base["AS_이벤트수"] > 0
    base["교환발생"] = base["교환_이벤트수"] > 0
    base["반품발생"] = base["반품_이벤트수"] > 0
    base["취소발생"] = base["취소_이벤트수"] > 0

    def _final(row) -> str:
        if row["반품발생"]:
            return "반품"
        if row["교환발생"]:
            return "교환"
        if row["AS발생"]:
            return "AS"
        if row["취소발생"]:
            return "취소"
        return "정상"

    base["최종상태"] = base.apply(_final, axis=1)
    return base

@st.cache_data(ttl=300, show_spinner=False)
def process_data(order_df, delivery_df):
    """
    로드된 데이터프레임을 전처리하여 분석용 데이터 생성
    Returns:
        order_df (가공됨), delivery_df (가공됨), ana_df (분석용 필터링됨)
    """
    
    # 캐시 안정성을 위해 입력 원본을 복사해서 가공
    order_df = order_df.copy() if order_df is not None else None
    delivery_df = delivery_df.copy() if delivery_df is not None else None

    # 전역 기준 통일: 청호나이스 현황판은 매출처 '청호나이스'만 사용
    if order_df is not None and not order_df.empty:
        order_df = filter_cheongho(order_df)
    if delivery_df is not None and not delivery_df.empty:
        delivery_df = filter_cheongho(delivery_df)

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
