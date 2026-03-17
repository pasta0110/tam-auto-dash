from __future__ import annotations

from datetime import date as _date

import pandas as pd


def safe_to_datetime(s: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(s, errors="coerce")
    except Exception:
        return pd.to_datetime(pd.Series([None] * len(s)), errors="coerce")


def to_date(d):
    if isinstance(d, _date) and not hasattr(d, "date"):
        return d
    return d.date()


def filter_order_for_tab1(order_df: pd.DataFrame) -> pd.DataFrame:
    if order_df is None or order_df.empty:
        return order_df
    df = order_df.copy()
    mask = pd.Series(True, index=df.index)
    if "매출처" in df.columns:
        mask &= df["매출처"].astype(str).eq("청호나이스")
    if "주문유형" in df.columns:
        mask &= df["주문유형"].astype(str).eq("정상")
    if "주문상태" in df.columns:
        mask &= ~df["주문상태"].astype(str).eq("주문취소")
    return df[mask].copy()


def filter_delivery_for_tab1(delivery_df: pd.DataFrame) -> pd.DataFrame:
    if delivery_df is None or delivery_df.empty:
        return delivery_df
    df = delivery_df.copy()
    mask = pd.Series(True, index=df.index)
    if "매출처" in df.columns:
        mask &= df["매출처"].astype(str).eq("청호나이스")
    if "주문유형" in df.columns:
        mask &= ~df["주문유형"].astype(str).eq("AS")
    if "주문상태" in df.columns:
        mask &= ~df["주문상태"].astype(str).eq("주문취소")
    if "배송유형" in df.columns:
        mask &= ~df["배송유형"].astype(str).eq("회수")
    if "배송상태" in df.columns:
        mask &= ~df["배송상태"].astype(str).eq("미설치")
    if "상품명" in df.columns:
        mask &= ~df["상품명"].astype(str).str.contains("쿨패드-", na=False)
    return df[mask].copy()


def ana_df_for_tab1(delivery_df: pd.DataFrame) -> pd.DataFrame:
    if delivery_df is None or delivery_df.empty:
        return delivery_df
    status_col = "배송상태" if "배송상태" in delivery_df.columns else "delivery_stat_nm"
    if status_col not in delivery_df.columns or "주문유형" not in delivery_df.columns:
        return delivery_df
    return delivery_df[
        (delivery_df[status_col].astype(str).str.contains("완료|4", na=False))
        & (delivery_df["주문유형"].astype(str).str.contains("정상", na=False))
    ].copy()


def split_month_day_df(df: pd.DataFrame, date_col: str, y_date, m_key: str, yesterday_str: str):
    dt = safe_to_datetime(df[date_col]) if date_col in df.columns else pd.Series([], dtype="datetime64[ns]")
    if dt.notna().any():
        month_start = pd.Timestamp(year=y_date.year, month=y_date.month, day=1)
        curr = df[(dt >= month_start) & (dt.dt.date <= y_date)].copy()
        day = df[dt.dt.date == y_date].copy()
    else:
        curr = df[df[date_col].astype(str).str.contains(m_key, na=False)].copy()
        day = curr[curr[date_col].astype(str).str.contains(yesterday_str, na=False)].copy()
    return curr, day


def build_main_rows(curr_df: pd.DataFrame, day_df: pd.DataFrame, date_header: str) -> pd.DataFrame:
    rows = []
    for cat in ["매트리스", "파운데이션", "프레임"]:
        if cat == "프레임":
            m = curr_df[curr_df["품목구분"] == cat].shape[0]
            d = day_df[day_df["품목구분"] == cat].shape[0]
        else:
            m = int(curr_df[curr_df["품목구분"] == cat]["수량"].sum())
            d = int(day_df[day_df["품목구분"] == cat]["수량"].sum())
        rows.append({"품목": cat, "당월 합계": m, date_header: d})
    out = pd.DataFrame(rows)
    out.loc[len(out)] = ["합계", out["당월 합계"].sum(), out[date_header].sum()]
    return out


def build_panel_rows(curr_df: pd.DataFrame, day_df: pd.DataFrame, date_header: str, total_label: str) -> pd.DataFrame:
    rows = []
    for p_num in ["01", "05"]:
        col_name = f"is_판넬{p_num}"
        m = int(curr_df[curr_df[col_name] == True]["수량"].sum()) if col_name in curr_df.columns else 0
        d = int(day_df[day_df[col_name] == True]["수량"].sum()) if col_name in day_df.columns else 0
        rows.append({"품목": f"판넬{p_num}", "당월 합계": m, date_header: d})
    out = pd.DataFrame(rows)
    out.loc[len(out)] = [total_label, out["당월 합계"].sum(), out[date_header].sum()]
    return out

