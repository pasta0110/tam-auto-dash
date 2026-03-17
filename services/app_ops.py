import streamlit as st
import config


def should_show_ops() -> bool:
    try:
        q_ops = str(st.query_params.get("ops", "0")) == "1"
    except Exception:
        q_ops = False
    try:
        secret_ops = bool(st.secrets.get("SHOW_OPS_PANEL", False))
    except Exception:
        secret_ops = False
    return q_ops or secret_ops


def render_ops_panel(
    selected_view: str,
    contract_source: str,
    process_source: str,
    perf: dict,
    order_df,
    delivery_df,
    ana_df,
    uploader_status: dict,
    integrity_alert: dict,
    hash_ok,
):
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
                "integrity_alert": integrity_alert or {},
            }
        )
        if hash_ok is False:
            st.warning(
                "무결성(meta-hash) 불일치 상태입니다. "
                "일반 사용자 화면에는 숨김 처리되며, 운영자 텔레그램으로만 알림 전송합니다."
            )
