import time
import streamlit as st

from data_processor import process_data
from services.pipeline_cache import build_expected_meta, load_processed_snapshot, save_processed_snapshot
from services.app_runtime import file_sig


def get_processed_payload(run_meta: dict, order_path: str, delivery_path: str):
    order_sig = file_sig(order_path)
    delivery_sig = file_sig(delivery_path)
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
            process_source = "fresh_compute"
        else:
            process_source = "disk_snapshot"
        st.session_state[state_key] = expected_meta
        st.session_state[state_payload] = payload
    elapsed = round(time.perf_counter() - t1, 4)
    return payload, expected_meta, process_source, elapsed


def ensure_payload_computed(payload, expected_meta, raw_order_df, raw_delivery_df):
    if payload is not None:
        return payload
    p_order, p_delivery, p_ana = process_data(raw_order_df, raw_delivery_df)
    payload = {"order_df": p_order, "delivery_df": p_delivery, "ana_df": p_ana}
    save_processed_snapshot(p_order, p_delivery, p_ana, expected_meta)
    st.session_state["_processed_data_payload"] = payload
    return payload
