from __future__ import annotations

import pandas as pd

from tabs.tab1_5.metrics import build_order_month_summary, build_r14_summary, kpi_table


def build_tab1_5_pack(order_df: pd.DataFrame, delivery_df: pd.DataFrame) -> dict:
    kpi_df = kpi_table(delivery_df)
    om_all = build_order_month_summary(order_df, delivery_df)
    r14 = build_r14_summary(order_df, delivery_df)
    return {"kpi_df": kpi_df, "om_all": om_all, "r14": r14}
