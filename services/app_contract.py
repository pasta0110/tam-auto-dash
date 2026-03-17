import time
import streamlit as st

from services.data_contract import validate_raw_inputs
from services.app_runtime import file_sig


def run_contract_gate(raw_order_df, raw_delivery_df, run_meta: dict, order_path: str, delivery_path: str):
    t0 = time.perf_counter()
    _order_sig = file_sig(order_path)
    _delivery_sig = file_sig(delivery_path)
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
    elapsed = round(time.perf_counter() - t0, 4)
    return errors, warnings, contract_source, elapsed
