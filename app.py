# app.py
# 메인 실행 파일 (진입점)

import streamlit as st
import pandas as pd
import config
from utils.date_utils import get_current_context
import data_loader
from data_processor import process_data

# 탭 모듈 임포트 (각 기능을 담당)
from tabs import tab1_summary, tab1_5_insights, tab2_delivery, tab3_prediction, tab4_validation, tab5_map


def _order_month_coverage(order_df, max_rows=40000):
    """
    최신 월부터 역순으로 '월 전체'를 누적해 max_rows에 가장 근접한 범위를 계산.
    예) 최신~2025-05까지 누적 38,294건
    """
    if order_df is None or order_df.empty:
        return None

    date_col = None
    for c in ["배송예정일", "등록일", "주문등록일"]:
        if c in order_df.columns:
            date_col = c
            break
    if date_col is None:
        return None

    dt = pd.to_datetime(order_df[date_col], errors="coerce")
    tmp = order_df.loc[dt.notna()].copy()
    if tmp.empty:
        return None

    tmp["_ym"] = dt.loc[dt.notna()].dt.strftime("%Y-%m")
    monthly = tmp.groupby("_ym", as_index=False).size().rename(columns={"size": "건수"})
    monthly["월일자"] = pd.to_datetime(monthly["_ym"] + "-01", errors="coerce")
    monthly = monthly.dropna(subset=["월일자"]).sort_values("월일자", ascending=False)
    if monthly.empty:
        return None

    include_months = []
    cum = 0
    for _, r in monthly.iterrows():
        m = str(r["_ym"])
        c = int(r["건수"])
        if include_months and (cum + c > max_rows):
            break
        include_months.append(m)
        cum += c

    if not include_months:
        first = monthly.iloc[0]
        include_months = [str(first["_ym"])]
        cum = int(first["건수"])

    return {
        "latest_month": include_months[0],
        "oldest_month": include_months[-1],
        "months": len(include_months),
        "rows": int(cum),
        "max_rows": int(max_rows),
    }

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
raw_order_df, raw_delivery_df = data_loader.load_raw_data()
snapshot = getattr(data_loader, "get_data_snapshot_info", lambda: {})()
run_meta = getattr(data_loader, "get_erp_run_meta", lambda: {})()
get_commit_time = getattr(data_loader, "get_github_last_commit_time", lambda _path: None)

# 4. 날짜 컨텍스트 확보 (오늘, 어제, 이번 달 등)
ctx = get_current_context()

parts = []
if run_meta:
    extracted = run_meta.get("extracted_at_kst")
    committed = run_meta.get("commit_at_kst")
    if extracted:
        parts.append(f"ERP 추출: {extracted}")
    if committed:
        parts.append(f"GitHub 업로드(커밋): {committed}")
    if run_meta.get("order_rows") is not None and run_meta.get("delivery_rows") is not None:
        parts.append(f"rows: order={run_meta.get('order_rows')}, delivery={run_meta.get('delivery_rows')}")

# fallback 1: GitHub 마지막 커밋 시각 (Streamlit Cloud에서 'local mtime'은 배포 시각이라 의미 없음)
if not parts:
    order_commit = get_commit_time("order.csv")
    delivery_commit = get_commit_time("delivery.csv")
    if order_commit or delivery_commit:
        parts.append(f"GitHub 커밋: order.csv={order_commit or 'unknown'} | delivery.csv={delivery_commit or 'unknown'}")

# fallback 2: 헤더 Last-Modified
if not parts and snapshot:
    lm_o = snapshot.get("order_last_modified") or snapshot.get("order_mtime_kst")
    lm_d = snapshot.get("delivery_last_modified") or snapshot.get("delivery_mtime_kst")
    if lm_o or lm_d:
        parts.append(f"Last-Modified: order.csv={lm_o or 'unknown'} | delivery.csv={lm_d or 'unknown'}")

if parts:
    cov = _order_month_coverage(raw_order_df, max_rows=40000)
    if cov:
        parts.append(
            "주문 4만건 기준 월범위: "
            f"{cov['oldest_month']}~{cov['latest_month']} "
            f"(월전체 {cov['months']}개, 누적 {cov['rows']:,}/{cov['max_rows']:,})"
        )
    st.caption("데이터 기준: " + " | ".join(parts))

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
