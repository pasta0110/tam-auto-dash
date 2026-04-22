# app.py
# 메인 실행 파일 (진입점)

import streamlit as st
import config
import time
from utils.date_utils import get_current_context
import data_loader
from services.app_runtime import (
    build_caption_parts,
    notify_integrity_mismatch_once,
)
from services.auth_security import enforce_auth_gate
from services.app_contract import run_contract_gate
from services.app_processed import get_processed_payload, ensure_payload_computed
from services.app_ops import should_show_ops, render_ops_panel

# 탭 모듈 임포트 (각 기능을 담당)
from tabs import tab1_summary, tab1_5_insights, tab2_delivery, tab2_5_exception, tab3_prediction, tab4_validation, tab5_map

# 1. 페이지 기본 설정 (가장 먼저 실행되어야 함)
st.set_page_config(
    page_title=config.APP_TITLE,
    layout="wide",
    page_icon=config.APP_ICON
)

# 2. 전역 스타일 적용 (CSS)
st.markdown(config.CSS_STYLE, unsafe_allow_html=True)

# 2.3 사이드바 토글(넣기/빼기)
if "ui_sidebar_hidden" not in st.session_state:
    st.session_state["ui_sidebar_hidden"] = False

toggle_label = "📂 메뉴 펼치기" if st.session_state["ui_sidebar_hidden"] else "📁 메뉴 접기"
if st.button(toggle_label, key="toggle_sidebar_btn"):
    st.session_state["ui_sidebar_hidden"] = not st.session_state["ui_sidebar_hidden"]
    st.rerun()

if st.session_state["ui_sidebar_hidden"]:
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"] {display: none !important;}
        </style>
        """,
        unsafe_allow_html=True,
    )

# 2.5 선택형 보안 게이트 (AUTH_ENABLED=true일 때만 작동)
enforce_auth_gate()

# 3. 데이터 로드 및 전처리
# (캐싱은 data_loader 내부에서 처리됨)
load_result = data_loader.load_raw_data_result()
raw_order_df, raw_delivery_df = load_result.get("order_df"), load_result.get("delivery_df")
snapshot = getattr(data_loader, "get_data_snapshot_info", lambda: {})()
run_meta = getattr(data_loader, "get_erp_run_meta", lambda: {})()
uploader_status = getattr(data_loader, "get_uploader_status", lambda: {})()
get_commit_time = getattr(data_loader, "get_github_last_commit_time", lambda _path: None)

# 4. 날짜 컨텍스트 확보 (오늘, 어제, 이번 달 등)
ctx = get_current_context()


integrity_alert = {}
parts, hash_ok = build_caption_parts(run_meta or {}, snapshot or {}, raw_order_df, get_commit_time)

if parts:
    st.caption("데이터 기준: " + " | ".join(parts))

if hash_ok is False:
    integrity_alert = notify_integrity_mismatch_once(
        (run_meta or {}).get("commit_at_kst"),
        (run_meta or {}).get("extracted_at_kst"),
        (run_meta or {}).get("order_rows"),
        (run_meta or {}).get("delivery_rows"),
    )

if raw_order_df is not None and raw_delivery_df is not None:
    perf = {}
    errors, warnings, contract_source, contract_elapsed = run_contract_gate(
        raw_order_df,
        raw_delivery_df,
        run_meta or {},
        config.ORDER_CSV_PATH,
        config.DELIVERY_CSV_PATH,
    )
    perf["contract_validation_sec"] = contract_elapsed
    if warnings:
        with st.expander(f"데이터 계약 경고 {len(warnings)}건", expanded=False):
            for w in warnings:
                st.warning(f"[{w.code}] {w.message}")
    if errors:
        for e in errors:
            st.error(f"[{e.code}] {e.message}")
        st.stop()

    payload, expected_meta, process_source, process_elapsed = get_processed_payload(
        run_meta or {},
        config.ORDER_CSV_PATH,
        config.DELIVERY_CSV_PATH,
    )
    payload = ensure_payload_computed(payload, expected_meta, raw_order_df, raw_delivery_df)
    perf["process_prepare_sec"] = process_elapsed

    order_df, delivery_df, ana_df = payload["order_df"], payload["delivery_df"], payload["ana_df"]
    cache_key = f"{expected_meta.get('schema')}|{expected_meta.get('order_sig')}|{expected_meta.get('delivery_sig')}|{expected_meta.get('order_sha256')}|{expected_meta.get('delivery_sha256')}"

    # 5. 메인 UI 구성 (사이드바 메뉴에서 선택된 화면만 실행)
    views = [
        "📋 1. 종합 현황",
        "📌 1.5 인사이트",
        "📈 2. 배송사별 분석",
        "⚠️ 2.5 운영 예외 큐",
        "🚀 3. 당월 출고 예측",
        "🔍 4. 예측 모델 검증",
        "📍 5. 배송 지도",
    ]
    with st.sidebar:
        st.markdown("### 메뉴")
        selected_view = st.radio(
            "메뉴",
            views,
            index=0,
            label_visibility="collapsed",
            key="main_view",
        )

    t_tab = time.perf_counter()
    if selected_view == views[0]:
        tab1_summary.render(order_df, delivery_df, ana_df, ctx)
    elif selected_view == views[1]:
        tab1_5_insights.render(order_df, delivery_df, ctx, cache_key=cache_key)
    elif selected_view == views[2]:
        tab2_delivery.render(ana_df, run_meta=run_meta, cache_key=cache_key)
    elif selected_view == views[3]:
        tab2_5_exception.render(delivery_df, ctx, cache_key=cache_key)
    elif selected_view == views[4]:
        tab3_prediction.render(ana_df, ctx, cache_key=cache_key)
    elif selected_view == views[5]:
        tab4_validation.render(ana_df, ctx, cache_key=cache_key)
    else:
        tab5_map.render(ana_df, cache_key=cache_key)
    perf["selected_tab_render_sec"] = round(time.perf_counter() - t_tab, 4)

    if should_show_ops():
        render_ops_panel(
            selected_view=selected_view,
            contract_source=contract_source,
            process_source=process_source,
            perf=perf,
            order_df=order_df,
            delivery_df=delivery_df,
            ana_df=ana_df,
            uploader_status=uploader_status or {},
            integrity_alert=integrity_alert or {},
            hash_ok=hash_ok,
        )

else:
    st.error(f"데이터를 불러올 수 없습니다: {load_result.get('error_message') or '원인 미상'}")
    diagnostics = load_result.get("diagnostics") or {}
    if diagnostics:
        with st.expander("로딩 진단 상세(원인 추적)", expanded=False):
            for target in ["order", "delivery"]:
                d = diagnostics.get(target) or {}
                if not d:
                    continue
                st.markdown(f"**{target}.csv**")
                st.write(f"- local_path: `{d.get('local_path')}`")
                st.write(f"- remote_url: `{d.get('remote_url')}`")
                st.write(f"- selected_source: `{d.get('selected_source')}`")
                st.write(f"- local_error: `{d.get('local_error')}`")
                st.write(f"- remote_error: `{d.get('remote_error')}`")
            if diagnostics.get("unexpected_error"):
                st.write(f"- unexpected_error: `{diagnostics.get('unexpected_error')}`")
