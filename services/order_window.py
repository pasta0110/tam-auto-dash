import pandas as pd


def order_month_coverage(order_df, max_rows=40000):
    """
    최신 월부터 역순으로 '월 전체'를 누적해 max_rows에 가장 근접한 범위를 계산.
    """
    if order_df is None or order_df.empty:
        return None

    date_col = None
    for c in ["배송예정일", "등록일", "주문등록일"]:
        if c in order_df.columns:
            date_col = c
            break
    if date_col is None:
        return None

    dt = pd.to_datetime(order_df[date_col], errors="coerce")
    tmp = order_df.loc[dt.notna()].copy()
    if tmp.empty:
        return None

    tmp["_ym"] = dt.loc[dt.notna()].dt.strftime("%Y-%m")
    monthly = tmp.groupby("_ym", as_index=False).size().rename(columns={"size": "건수"})
    monthly["월일자"] = pd.to_datetime(monthly["_ym"] + "-01", errors="coerce")
    monthly = monthly.dropna(subset=["월일자"]).sort_values("월일자", ascending=False)
    if monthly.empty:
        return None

    include_months = []
    cum = 0
    for _, r in monthly.iterrows():
        m = str(r["_ym"])
        c = int(r["건수"])
        if include_months and (cum + c > max_rows):
            break
        include_months.append(m)
        cum += c

    if not include_months:
        first = monthly.iloc[0]
        include_months = [str(first["_ym"])]
        cum = int(first["건수"])

    return {
        "latest_month": include_months[0],
        "oldest_month": include_months[-1],
        "months": len(include_months),
        "rows": int(cum),
        "max_rows": int(max_rows),
    }

