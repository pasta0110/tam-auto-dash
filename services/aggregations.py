from __future__ import annotations

import pandas as pd


def aggregate_month_center_counts(
    df: pd.DataFrame,
    month_key_col: str = "연월_키",
    month_dt_col: str = "월일자",
    center_col: str = "배송사_정제",
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=[month_key_col, month_dt_col, "지역센터", "완료건수"])

    required = {month_key_col, month_dt_col, center_col}
    if not required.issubset(set(df.columns)):
        return pd.DataFrame(columns=[month_key_col, month_dt_col, "지역센터", "완료건수"])

    return (
        df.groupby([month_key_col, month_dt_col, center_col], as_index=False)
        .size()
        .rename(columns={center_col: "지역센터", "size": "완료건수"})
    )

