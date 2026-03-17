import os
import streamlit as st

import config
from services.integrity import meta_hash_status
from services.notifiers import build_telegram_notifier
from services.order_window import order_month_coverage


def file_sig(path: str):
    try:
        if not path or not os.path.exists(path):
            return (None, None)
        return (int(os.path.getsize(path)), int(os.path.getmtime(path)))
    except Exception:
        return (None, None)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_meta_hash_status(meta_o, meta_d, order_path, delivery_path, order_sig, delivery_sig):
    return meta_hash_status(meta_o, meta_d, order_path, delivery_path)


@st.cache_data(ttl=1800, show_spinner=False)
def notify_integrity_mismatch_once(commit_at_kst, extracted_at_kst, order_rows, delivery_rows):
    token = str(st.secrets.get("TELEGRAM_BOT_TOKEN", os.getenv("TELEGRAM_BOT_TOKEN", ""))).strip()
    chat_id = str(st.secrets.get("TELEGRAM_CHAT_ID", os.getenv("TELEGRAM_CHAT_ID", ""))).strip()
    notifier = build_telegram_notifier(token, chat_id)
    if not token or not chat_id:
        return {"sent": False, "reason": "missing_telegram_secret"}
    msg = (
        "⚠️ 무결성 경고\n"
        "meta-hash 불일치 감지\n"
        f"ERP 추출: {extracted_at_kst or '-'}\n"
        f"GitHub 커밋: {commit_at_kst or '-'}\n"
        f"rows: order={order_rows or '-'}, delivery={delivery_rows or '-'}\n"
        "조치: 업로더 1회 수동 실행 후 앱 새로고침"
    )
    ok = notifier.send(msg)
    return {"sent": bool(ok), "reason": "ok" if ok else "send_failed"}


def build_caption_parts(run_meta: dict, snapshot: dict, raw_order_df, get_commit_time):
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
        hash_ok = cached_meta_hash_status(
            meta_o,
            meta_d,
            config.ORDER_CSV_PATH,
            config.DELIVERY_CSV_PATH,
            file_sig(config.ORDER_CSV_PATH),
            file_sig(config.DELIVERY_CSV_PATH),
        )
        if hash_ok is True:
            parts.append("무결성: ✅ meta-hash 일치")
        elif hash_ok is False:
            parts.append("무결성: ❌ meta-hash 불일치")

    if not parts:
        order_commit = get_commit_time("order.csv")
        delivery_commit = get_commit_time("delivery.csv")
        if order_commit or delivery_commit:
            parts.append(f"GitHub 커밋: order.csv={order_commit or 'unknown'} | delivery.csv={delivery_commit or 'unknown'}")

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
    return parts, hash_ok
