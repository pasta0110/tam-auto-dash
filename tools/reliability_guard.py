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

    results = {
        "tab2_snapshot_equals_direct": bool(tab2_ok),
        "kpi_rows": int(len(kpi)),
        "order_month_rows": int(len(om)),
        "r14_rows": int(len(r14)),
        "order_rows": int(len(order_df)),
        "delivery_rows": int(len(delivery_df)),
    }
    print(json.dumps(results, ensure_ascii=False, indent=2))
    failed = (not tab2_ok) or (len(kpi) == 0) or (len(om) == 0) or (len(r14) == 0)
    if args.strict and failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
