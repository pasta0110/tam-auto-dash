# app.py
# 메인 실행 파일 (진입점)

import streamlit as st
import config
import os
from utils.date_utils import get_current_context
import data_loader
from data_processor import process_data
from services.order_window import order_month_coverage
from services.integrity import meta_hash_status
from services.data_contract import validate_raw_inputs

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
raw_order_df, raw_delivery_df = data_loader.load_raw_data()
snapshot = getattr(data_loader, "get_data_snapshot_info", lambda: {})()
run_meta = getattr(data_loader, "get_erp_run_meta", lambda: {})()
get_commit_time = getattr(data_loader, "get_github_last_commit_time", lambda _path: None)

# 4. 날짜 컨텍스트 확보 (오늘, 어제, 이번 달 등)
ctx = get_current_context()


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_meta_hash_status(meta_o, meta_d, order_path, delivery_path, order_sig, delivery_sig):
    return meta_hash_status(meta_o, meta_d, order_path, delivery_path)


def _file_sig(path: str):
    try:
        if not path or not os.path.exists(path):
            return (None, None)
        return (int(os.path.getsize(path)), int(os.path.getmtime(path)))
    except Exception:
        return (None, None)

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
    meta_o = run_meta.get("order_sha256")
    meta_d = run_meta.get("delivery_sha256")
    hash_ok = _cached_meta_hash_status(
        meta_o,
        meta_d,
        config.ORDER_CSV_PATH,
        config.DELIVERY_CSV_PATH,
        _file_sig(config.ORDER_CSV_PATH),
        _file_sig(config.DELIVERY_CSV_PATH),
    )
    if hash_ok is True:
        parts.append("무결성: ✅ meta-hash 일치")
    elif hash_ok is False:
        parts.append("무결성: ❌ meta-hash 불일치")

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
    cov = order_month_coverage(raw_order_df, max_rows=40000)
    if cov:
        parts.append(
            "주문 4만건 기준 월범위: "
            f"{cov['oldest_month']}~{cov['latest_month']} "
            f"(월전체 {cov['months']}개, 누적 {cov['rows']:,}/{cov['max_rows']:,})"
        )
    st.caption("데이터 기준: " + " | ".join(parts))

if raw_order_df is not None and raw_delivery_df is not None:
    errors, warnings = validate_raw_inputs(raw_order_df, raw_delivery_df)
    if warnings:
        with st.expander(f"데이터 계약 경고 {len(warnings)}건", expanded=False):
            for w in warnings:
                st.warning(f"[{w.code}] {w.message}")
    if errors:
        for e in errors:
            st.error(f"[{e.code}] {e.message}")
        st.stop()

    # 데이터 가공 (컬럼 추가, 필터링 등)
    order_df, delivery_df, ana_df = process_data(raw_order_df, raw_delivery_df)

    # 5. 메인 UI 구성 (선택된 화면만 실행)
    views = [
        "📋 1. 종합 현황",
        "📌 1.5 인사이트",
        "📈 2. 배송사별 분석",
        "🚀 3. 당월 출고 예측",
        "🔍 4. 예측 모델 검증",
        "📍 5. 배송 지도",
    ]
    selected_view = st.radio("메뉴", views, horizontal=True, label_visibility="collapsed", key="main_view")

    if selected_view == views[0]:
        tab1_summary.render(order_df, delivery_df, ana_df, ctx)
    elif selected_view == views[1]:
        tab1_5_insights.render(order_df, delivery_df, ctx)
    elif selected_view == views[2]:
        tab2_delivery.render(ana_df, run_meta=run_meta)
    elif selected_view == views[3]:
        tab3_prediction.render(ana_df, ctx)
    elif selected_view == views[4]:
        tab4_validation.render(ana_df, ctx)
    else:
        tab5_map.render(ana_df)

else:
    st.error("데이터를 불러올 수 없습니다. 네트워크 상태를 확인해주세요.")
