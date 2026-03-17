from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import config


SNAPSHOT_DIR = Path("cache")
PROCESSED_DATA_PATH = SNAPSHOT_DIR / "processed_data.pkl"
PROCESSED_META_PATH = SNAPSHOT_DIR / "processed_meta.json"
SCHEMA_VERSION = f"processed_{config.CACHE_SCHEMA_VERSION}"


def build_expected_meta(
    order_sig: tuple[Any, Any],
    delivery_sig: tuple[Any, Any],
    order_sha: str = "",
    delivery_sha: str = "",
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "order_sig": [order_sig[0], order_sig[1]],
        "delivery_sig": [delivery_sig[0], delivery_sig[1]],
        "order_sha256": str(order_sha or ""),
        "delivery_sha256": str(delivery_sha or ""),
    }


def load_processed_snapshot(expected_meta: dict[str, Any]):
    if not PROCESSED_DATA_PATH.exists() or not PROCESSED_META_PATH.exists():
        return None
    try:
        saved_meta = json.loads(PROCESSED_META_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    if saved_meta != expected_meta:
        return None
    try:
        payload = pd.read_pickle(PROCESSED_DATA_PATH)
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None
    if not {"order_df", "delivery_df", "ana_df"}.issubset(set(payload.keys())):
        return None
    return payload


def save_processed_snapshot(order_df, delivery_df, ana_df, meta: dict[str, Any]) -> None:
    try:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        payload = {"order_df": order_df, "delivery_df": delivery_df, "ana_df": ana_df}
        pd.to_pickle(payload, PROCESSED_DATA_PATH)
        PROCESSED_META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return
