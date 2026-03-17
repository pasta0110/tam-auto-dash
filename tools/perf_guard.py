import json
import time
import sys
import argparse
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import data_loader
from data_processor import process_data
from tabs.tab1_5.metrics import build_order_month_summary, build_r14_summary
from tabs.tab2.metrics import build_total_compare_with_snapshot, prepare_work_df
from tabs import tab5_map


def timed(name, fn):
    t0 = time.perf_counter()
    out = fn()
    return name, round(time.perf_counter() - t0, 4), out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-tab2-total", type=float, default=None, help="Fail if tab2_selected_estimated_total exceeds this value.")
    parser.add_argument("--loops", type=int, default=2, help="Number of perf loops (first=cold, others=warm).")
    args = parser.parse_args()

    loops = max(1, int(args.loops))
    records = []
    for i in range(loops):
        report = {"loop": i + 1}
        _, t_load, loaded = timed("load_raw_data", lambda: data_loader.load_raw_data())
        order_df, delivery_df = loaded
        report["load_raw_data"] = t_load

        _, t_proc, processed = timed("process_data", lambda: process_data(order_df, delivery_df))
        order_df, delivery_df, ana_df = processed
        report["process_data"] = t_proc

        work_df = prepare_work_df(ana_df)
        _, t_tab2, _ = timed(
            "tab2_compare_with_snapshot",
            lambda: build_total_compare_with_snapshot(work_df, run_meta=data_loader.get_erp_run_meta()),
        )
        report["tab2_compare_with_snapshot"] = t_tab2

        _, t_om, _ = timed("tab1_5_order_month_summary", lambda: build_order_month_summary(order_df, delivery_df))
        _, t_r14, _ = timed("tab1_5_r14_summary", lambda: build_r14_summary(order_df, delivery_df))
        base_cols = [c for c in ["주소", "상품명", "배송사_정제", "배송예정일", "주문등록일"] if c in ana_df.columns]
        if "주소" in base_cols:
            src_df = ana_df[base_cols].copy()
            csv_path = str(ROOT / "coords.csv")
            csv_mtime = (ROOT / "coords.csv").stat().st_mtime if (ROOT / "coords.csv").exists() else 0.0
            _, t_map_prep, _ = timed(
                "tab5_map_prepare_base",
                lambda: tab5_map._prepare_map_base_cached(src_df, csv_path, csv_mtime),
            )
        else:
            t_map_prep = 0.0
        report["tab1_5_order_month_summary"] = t_om
        report["tab1_5_r14_summary"] = t_r14
        report["tab5_map_prepare_base"] = t_map_prep
        report["tab2_selected_estimated_total"] = round(t_load + t_proc + t_tab2, 4)
        report["legacy_extra_if_all_tabs_execute"] = round(t_om + t_r14, 4)
        records.append(report)

    cold = records[0]
    warm = records[1:] if len(records) > 1 else records
    warm_avg = {
        "load_raw_data": round(mean([r["load_raw_data"] for r in warm]), 4),
        "process_data": round(mean([r["process_data"] for r in warm]), 4),
        "tab2_compare_with_snapshot": round(mean([r["tab2_compare_with_snapshot"] for r in warm]), 4),
        "tab2_selected_estimated_total": round(mean([r["tab2_selected_estimated_total"] for r in warm]), 4),
        "tab1_5_order_month_summary": round(mean([r["tab1_5_order_month_summary"] for r in warm]), 4),
        "tab1_5_r14_summary": round(mean([r["tab1_5_r14_summary"] for r in warm]), 4),
        "tab5_map_prepare_base": round(mean([r["tab5_map_prepare_base"] for r in warm]), 4),
    }
    report = {"cold": cold, "warm_avg": warm_avg, "loops": records}

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.max_tab2_total is not None and warm_avg["tab2_selected_estimated_total"] > args.max_tab2_total:
        sys.exit(1)


if __name__ == "__main__":
    main()
