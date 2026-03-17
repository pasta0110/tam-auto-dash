import json
import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import data_loader
from data_processor import process_data
from tabs.tab1_5.metrics import build_order_month_summary, build_r14_summary, kpi_table
from tabs.tab2.metrics import build_total_compare, build_total_compare_with_snapshot, prepare_work_df


def normalize(df, sort_cols):
    if df is None:
        return None
    out = df.copy()
    for c in sort_cols:
        if c not in out.columns:
            out[c] = ""
    return out.sort_values(sort_cols).reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Fail process if checks are not satisfied.")
    args = parser.parse_args()

    order_df, delivery_df = data_loader.load_raw_data()
    order_df, delivery_df, ana_df = process_data(order_df, delivery_df)

    work_df = prepare_work_df(ana_df)
    direct, direct_months = build_total_compare(work_df)
    snap, snap_months = build_total_compare_with_snapshot(work_df, run_meta=data_loader.get_erp_run_meta())

    tab2_ok = (
        direct_months == snap_months
        and normalize(direct, ["연월_키", "월일자", "지역센터"]).equals(
            normalize(snap, ["연월_키", "월일자", "지역센터"])
        )
    )

    kpi = kpi_table(delivery_df)
    om = build_order_month_summary(order_df, delivery_df)
    r14 = build_r14_summary(order_df, delivery_df)

    # 추가 무결성 점검
    unique_ok = True
    kpi_vs_om_ok = True
    r14_bounds_ok = True

    if not om.empty and {"연월_키", "주문번호"}.issubset(set(om.columns)):
        dup_cnt = int(om.duplicated(subset=["연월_키", "주문번호"]).sum())
        unique_ok = dup_cnt == 0
    else:
        dup_cnt = -1

    if not kpi.empty and not om.empty:
        month_stats = (
            om.groupby("연월_키", as_index=False)
            .agg(
                전체=("주문번호", "size"),
                AS=("최종상태", lambda x: int((x == "AS").sum())),
                교환=("최종상태", lambda x: int((x == "교환").sum())),
                반품=("최종상태", lambda x: int((x == "반품").sum())),
                취소=("최종상태", lambda x: int((x == "취소").sum())),
            )
            .rename(columns={"연월_키": "월"})
        )
        merged = kpi.merge(month_stats, on="월", how="left", suffixes=("_kpi", "_om")).fillna(0)
        kpi_vs_om_ok = bool(
            (merged["전체_kpi"].astype(int) == merged["전체_om"].astype(int)).all()
            and (merged["AS_kpi"].astype(int) == merged["AS_om"].astype(int)).all()
            and (merged["교환_kpi"].astype(int) == merged["교환_om"].astype(int)).all()
            and (merged["반품_kpi"].astype(int) == merged["반품_om"].astype(int)).all()
            and (merged["취소_kpi"].astype(int) == merged["취소_om"].astype(int)).all()
        )

    if not r14.empty and {"R14", "R7"}.issubset(set(r14.columns)):
        r14_bounds_ok = bool(((r14["R14"] >= 0) & (r14["R7"] >= 0) & (r14["R7"] <= r14["R14"])).all())

    results = {
        "tab2_snapshot_equals_direct": bool(tab2_ok),
        "kpi_rows": int(len(kpi)),
        "order_month_rows": int(len(om)),
        "r14_rows": int(len(r14)),
        "order_rows": int(len(order_df)),
        "delivery_rows": int(len(delivery_df)),
        "order_month_unique_by_month_order": bool(unique_ok),
        "order_month_dup_count": int(dup_cnt),
        "kpi_vs_order_month_consistent": bool(kpi_vs_om_ok),
        "r14_bounds_valid": bool(r14_bounds_ok),
    }
    print(json.dumps(results, ensure_ascii=False, indent=2))
    failed = (
        (not tab2_ok)
        or (len(kpi) == 0)
        or (len(om) == 0)
        or (len(r14) == 0)
        or (not unique_ok)
        or (not kpi_vs_om_ok)
        or (not r14_bounds_ok)
    )
    if args.strict and failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
