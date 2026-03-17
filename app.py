# app.py
# 메인 실행 파일 (진입점)

import streamlit as st
import config
import os
import time
from utils.date_utils import get_current_context
import data_loader
from data_processor import process_data
from services.order_window import order_month_coverage
from services.integrity import meta_hash_status
from services.data_contract import validate_raw_inputs
from services.pipeline_cache import (
    build_expected_meta,
    load_processed_snapshot,
    save_processed_snapshot,
)

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
uploader_status = getattr(data_loader, "get_uploader_status", lambda: {})()
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
hash_ok = None
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

if hash_ok is False:
    st.warning(
        "무결성(meta-hash) 불일치가 감지되었습니다. "
        "업로더 수동 1회 실행 후 앱 리로드를 권장합니다. "
        "지속되면 order/delivery/meta 3파일이 같은 커밋에 포함됐는지 확인하세요."
    )

if raw_order_df is not None and raw_delivery_df is not None:
    perf = {}
    t0 = time.perf_counter()
    _order_sig = _file_sig(config.ORDER_CSV_PATH)
    _delivery_sig = _file_sig(config.DELIVERY_CSV_PATH)
    _order_sha = (run_meta or {}).get("order_sha256", "")
    _delivery_sha = (run_meta or {}).get("delivery_sha256", "")
    _contract_key = ("contract_v1", _order_sig, _delivery_sig, _order_sha, _delivery_sha)
    if st.session_state.get("_contract_key") != _contract_key:
        _errors, _warnings = validate_raw_inputs(raw_order_df, raw_delivery_df)
        st.session_state["_contract_key"] = _contract_key
        st.session_state["_contract_errors"] = _errors
        st.session_state["_contract_warnings"] = _warnings
        contract_source = "recomputed"
    else:
        contract_source = "session_cache"
    errors = st.session_state.get("_contract_errors", [])
    warnings = st.session_state.get("_contract_warnings", [])
    perf["contract_validation_sec"] = round(time.perf_counter() - t0, 4)
    if warnings:
        with st.expander(f"데이터 계약 경고 {len(warnings)}건", expanded=False):
            for w in warnings:
                st.warning(f"[{w.code}] {w.message}")
    if errors:
        for e in errors:
            st.error(f"[{e.code}] {e.message}")
        st.stop()

    # 데이터 가공 (컬럼 추가, 필터링 등): 리런 시 재가공을 피하기 위해 세션+디스크 스냅샷 재사용
    order_sig = _file_sig(config.ORDER_CSV_PATH)
    delivery_sig = _file_sig(config.DELIVERY_CSV_PATH)
    run_meta = run_meta or {}
    expected_meta = build_expected_meta(
        order_sig=order_sig,
        delivery_sig=delivery_sig,
        order_sha=run_meta.get("order_sha256", ""),
        delivery_sha=run_meta.get("delivery_sha256", ""),
    )

    state_key = "_processed_data_meta"
    state_payload = "_processed_data_payload"
    t1 = time.perf_counter()
    if st.session_state.get(state_key) == expected_meta and state_payload in st.session_state:
        payload = st.session_state[state_payload]
        process_source = "session_cache"
    else:
        payload = load_processed_snapshot(expected_meta)
        if payload is None:
            p_order, p_delivery, p_ana = process_data(raw_order_df, raw_delivery_df)
            payload = {"order_df": p_order, "delivery_df": p_delivery, "ana_df": p_ana}
            save_processed_snapshot(p_order, p_delivery, p_ana, expected_meta)
            process_source = "fresh_compute"
        else:
            process_source = "disk_snapshot"
        st.session_state[state_key] = expected_meta
        st.session_state[state_payload] = payload
    perf["process_prepare_sec"] = round(time.perf_counter() - t1, 4)

    order_df, delivery_df, ana_df = payload["order_df"], payload["delivery_df"], payload["ana_df"]
    cache_key = f"{expected_meta.get('schema')}|{expected_meta.get('order_sig')}|{expected_meta.get('delivery_sig')}|{expected_meta.get('order_sha256')}|{expected_meta.get('delivery_sha256')}"

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

    t_tab = time.perf_counter()
    if selected_view == views[0]:
        tab1_summary.render(order_df, delivery_df, ana_df, ctx)
    elif selected_view == views[1]:
        tab1_5_insights.render(order_df, delivery_df, ctx, cache_key=cache_key)
    elif selected_view == views[2]:
        tab2_delivery.render(ana_df, run_meta=run_meta, cache_key=cache_key)
    elif selected_view == views[3]:
        tab3_prediction.render(ana_df, ctx, cache_key=cache_key)
    elif selected_view == views[4]:
        tab4_validation.render(ana_df, ctx, cache_key=cache_key)
    else:
        tab5_map.render(ana_df, cache_key=cache_key)
    perf["selected_tab_render_sec"] = round(time.perf_counter() - t_tab, 4)

    try:
        q_ops = str(st.query_params.get("ops", "0")) == "1"
    except Exception:
        q_ops = False
    try:
        secret_ops = bool(st.secrets.get("SHOW_OPS_PANEL", False))
    except Exception:
        secret_ops = False
    if q_ops or secret_ops:
        with st.expander("⚙️ Ops Panel", expanded=False):
            st.write(
                {
                    "selected_view": selected_view,
                    "contract_source": contract_source,
                    "process_source": process_source,
                    "cache_schema": config.CACHE_SCHEMA_VERSION,
                    "perf": perf,
                    "rows": {
                        "order": int(len(order_df)) if order_df is not None else 0,
                        "delivery": int(len(delivery_df)) if delivery_df is not None else 0,
                        "ana": int(len(ana_df)) if ana_df is not None else 0,
                    },
                    "uploader_status": uploader_status or {},
                }
            )

else:
    st.error("데이터를 불러올 수 없습니다. 네트워크 상태를 확인해주세요.")
