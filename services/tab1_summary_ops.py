from __future__ import annotations

from datetime import date as _date

import pandas as pd

MAIN_PRODUCT_ROWS = ["매트리스(기존)", "매트리스(온열)", "매트리스 계", "파운데이션", "프레임"]


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
    for cat in MAIN_PRODUCT_ROWS:
        m = product_metric(curr_df, cat)
        d = product_metric(day_df, cat)
        rows.append({"품목": cat, "당월 합계": m, date_header: d})
    out = pd.DataFrame(rows)
    m_total = (
        product_metric(curr_df, "매트리스 계")
        + product_metric(curr_df, "파운데이션")
        + product_metric(curr_df, "프레임")
    )
    d_total = (
        product_metric(day_df, "매트리스 계")
        + product_metric(day_df, "파운데이션")
        + product_metric(day_df, "프레임")
    )
    out.loc[len(out)] = ["합계", m_total, d_total]
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


def _is_hot_mattress(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(False, index=pd.Index([]))
    name_col = df["상품명"].astype(str) if "상품명" in df.columns else pd.Series("", index=df.index)
    item_col = df["품목구분"].astype(str) if "품목구분" in df.columns else pd.Series("", index=df.index)
    return item_col.eq("매트리스") & name_col.str.contains("온열", na=False)


def _sum_qty(df: pd.DataFrame, mask: pd.Series) -> int:
    if "수량" not in df.columns:
        return int(mask.sum())
    return int(pd.to_numeric(df.loc[mask, "수량"], errors="coerce").fillna(0).sum())


def product_metric(df: pd.DataFrame, label: str) -> int:
    if df is None or df.empty:
        return 0

    item_col = df["품목구분"].astype(str) if "품목구분" in df.columns else pd.Series("", index=df.index)
    hot_mask = _is_hot_mattress(df)

    if label == "매트리스(온열)":
        return _sum_qty(df, hot_mask)
    if label == "매트리스(기존)":
        return _sum_qty(df, item_col.eq("매트리스") & ~hot_mask)
    if label == "매트리스 계":
        return _sum_qty(df, item_col.eq("매트리스"))
    if label == "파운데이션":
        return _sum_qty(df, item_col.eq("파운데이션"))
    if label == "프레임":
        return int(item_col.eq("프레임").sum())
    return 0
