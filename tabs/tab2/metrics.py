import json
from pathlib import Path

import pandas as pd
from services.aggregations import aggregate_month_center_counts
import config


REQUIRED_COLS = {"연월_키", "배송사_정제", "주문유형", "배송상태", "매출처"}
SNAPSHOT_DIR = Path("cache")
FIXED_COMPARE_PATH = SNAPSHOT_DIR / "tab2_fixed_compare.pkl"
FIXED_META_PATH = SNAPSHOT_DIR / "tab2_fixed_meta.json"


def prepare_work_df(ana_df: pd.DataFrame) -> pd.DataFrame:
    if ana_df is None or ana_df.empty:
        return pd.DataFrame()

    missing_cols = [c for c in REQUIRED_COLS if c not in ana_df.columns]
    if missing_cols:
        return pd.DataFrame()

    work_df = ana_df.copy()
    work_df = work_df[work_df["매출처"].astype(str).str.strip().eq("청호나이스")].copy()
    if work_df.empty:
        return pd.DataFrame()

    month_dt = pd.to_datetime(work_df["연월_키"].astype(str) + "-01", errors="coerce")
    work_df = work_df.loc[month_dt.notna()].copy()
    work_df["월일자"] = month_dt.loc[month_dt.notna()]
    work_df["연월_키"] = work_df["월일자"].dt.strftime("%Y-%m")
    return work_df


def build_total_compare(work_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    if work_df is None or work_df.empty:
        return pd.DataFrame(), []

    total_compare = aggregate_month_center_counts(work_df)
    all_months = (
        total_compare[["연월_키", "월일자"]]
        .drop_duplicates()
        .sort_values("월일자")["연월_키"]
        .tolist()
    )
    return total_compare, all_months


def _aggregate_month_center(df: pd.DataFrame) -> pd.DataFrame:
    return aggregate_month_center_counts(df)


def _expected_fixed_meta(run_meta: dict | None, last_fixed_month: str, fixed_rows: int) -> dict:
    run_meta = run_meta or {}
    return {
        "schema": f"tab2_fixed_{config.CACHE_SCHEMA_VERSION}",
        "delivery_sha256": str(run_meta.get("delivery_sha256", "") or ""),
        "order_sha256": str(run_meta.get("order_sha256", "") or ""),
        "last_fixed_month": str(last_fixed_month or ""),
        "fixed_rows": int(fixed_rows),
    }


def _load_fixed_snapshot(expected_meta: dict) -> pd.DataFrame | None:
    if not FIXED_COMPARE_PATH.exists() or not FIXED_META_PATH.exists():
        return None
    try:
        saved_meta = json.loads(FIXED_META_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    if saved_meta != expected_meta:
        return None
    try:
        snap = pd.read_pickle(FIXED_COMPARE_PATH)
    except Exception:
        return None
    required = {"연월_키", "월일자", "지역센터", "완료건수"}
    if not required.issubset(set(snap.columns)):
        return None
    return snap


def _save_fixed_snapshot(df_fixed_compare: pd.DataFrame, meta: dict) -> None:
    try:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        df_fixed_compare.to_pickle(FIXED_COMPARE_PATH)
        FIXED_META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # 스냅샷 저장 실패 시에도 기능은 계속 동작해야 함
        return


def build_total_compare_with_snapshot(work_df: pd.DataFrame, run_meta: dict | None = None) -> tuple[pd.DataFrame, list[str]]:
    if work_df is None or work_df.empty:
        return pd.DataFrame(), []

    latest_dt = work_df["월일자"].max()
    if pd.isna(latest_dt):
        return pd.DataFrame(), []
    current_month = latest_dt.strftime("%Y-%m")

    fixed_df = work_df[work_df["연월_키"] < current_month].copy()
    curr_df = work_df[work_df["연월_키"] == current_month].copy()

    last_fixed_month = fixed_df["연월_키"].max() if not fixed_df.empty else ""
    expected_meta = _expected_fixed_meta(run_meta, str(last_fixed_month), len(fixed_df))

    can_use_snapshot = bool(expected_meta["delivery_sha256"] and expected_meta["order_sha256"])
    fixed_compare = None
    if can_use_snapshot:
        fixed_compare = _load_fixed_snapshot(expected_meta)

    if fixed_compare is None:
        fixed_compare = _aggregate_month_center(fixed_df)
        if can_use_snapshot:
            _save_fixed_snapshot(fixed_compare, expected_meta)

    curr_compare = _aggregate_month_center(curr_df)
    total_compare = pd.concat([fixed_compare, curr_compare], ignore_index=True)
    if not total_compare.empty:
        total_compare = total_compare.sort_values(["월일자", "지역센터"]).reset_index(drop=True)
    all_months = (
        total_compare[["연월_키", "월일자"]]
        .drop_duplicates()
        .sort_values("월일자")["연월_키"]
        .tolist()
    )
    return total_compare, all_months


def bar_view_data(total_compare: pd.DataFrame, view_months: list[str]):
    if total_compare is None or total_compare.empty or not view_months:
        return pd.DataFrame(), pd.Series(dtype="int64"), []

    df_view = total_compare[total_compare["연월_키"].isin(view_months)].copy()
    monthly_totals = df_view.groupby("연월_키")["완료건수"].sum()
    month_labels = [f"{m}<br>[총 합계: {int(monthly_totals.get(m, 0)):,}건]" for m in view_months]
    return df_view, monthly_totals, month_labels


def dual_axis_data(total_compare: pd.DataFrame, center: str) -> pd.DataFrame:
    if total_compare is None or total_compare.empty:
        return pd.DataFrame()

    total_monthly = total_compare.groupby("연월_키", as_index=False)["완료건수"].sum().rename(columns={"완료건수": "전체건수"})
    v_monthly = (
        total_compare[total_compare["지역센터"] == center]
        .groupby("연월_키", as_index=False)["완료건수"]
        .sum()
        .rename(columns={"완료건수": "지역건수"})
    )
    df_combined = pd.merge(total_monthly, v_monthly, on="연월_키", how="left").fillna(0).sort_values("연월_키")
    df_combined["월일자"] = pd.to_datetime(df_combined["연월_키"] + "-01", errors="coerce")
    df_combined = df_combined.dropna(subset=["월일자"]).copy()
    return df_combined
