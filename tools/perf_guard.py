import json
import time
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import data_loader
from data_processor import process_data
from tabs.tab1_5.metrics import build_order_month_summary, build_r14_summary
from tabs.tab2.metrics import build_total_compare_with_snapshot, prepare_work_df


def timed(name, fn):
    t0 = time.perf_counter()
    out = fn()
    return name, round(time.perf_counter() - t0, 4), out


def main():
    report = {}

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
    report["tab1_5_order_month_summary"] = t_om
    report["tab1_5_r14_summary"] = t_r14

    report["tab2_selected_estimated_total"] = round(t_load + t_proc + t_tab2, 4)
    report["legacy_extra_if_all_tabs_execute"] = round(t_om + t_r14, 4)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
