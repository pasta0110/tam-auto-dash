# tabs/tab1_5_insights.py
# 1.5 인사이트 (월별 AS/교환/반품/취소율)

import pandas as pd
import streamlit as st


def _safe_to_datetime(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")


def _month_key(d: pd.Series) -> pd.Series:
    return d.dt.strftime("%Y-%m")


def _kpi_table(order_df: pd.DataFrame, delivery_df: pd.DataFrame, cutoff_date: pd.Timestamp) -> pd.DataFrame:
    """
    cutoff_date: 기준일(어제) 00:00 기준 date (Timestamp)
    - 분모: 정상(주문유형='정상')만
    - 기준일: 배송예정일 기준
    - 교환: 주문유형='AS' AND 배송유형='교환'
    """
    cutoff_day = cutoff_date.date()

    # --- 주문(취소율) ---
    o = order_df.copy()
    o_dt = _safe_to_datetime(o["배송예정일"]) if "배송예정일" in o.columns else pd.Series([], dtype="datetime64[ns]")
    if not o_dt.notna().any():
        return pd.DataFrame()
    o = o[o_dt.dt.date <= cutoff_day].copy()
    o["연월_키"] = _month_key(o_dt)

    o_norm = o[o["주문유형"].astype(str).eq("정상")].copy() if "주문유형" in o.columns else o.iloc[0:0].copy()
    o_cancel = (
        o_norm[o_norm["주문상태"].astype(str).eq("주문취소")].copy() if "주문상태" in o_norm.columns else o_norm.iloc[0:0].copy()
    )

    # --- 출고(AS/교환/반품) ---
    d = delivery_df.copy()
    d_dt = _safe_to_datetime(d["배송예정일"]) if "배송예정일" in d.columns else pd.Series([], dtype="datetime64[ns]")
    if not d_dt.notna().any():
        return pd.DataFrame()
    d = d[d_dt.dt.date <= cutoff_day].copy()
    d["연월_키"] = _month_key(d_dt)

    # 분모: 정상 출고(주문유형에 '정상' 포함)
    d_norm = d[d["주문유형"].astype(str).str.contains("정상", na=False)].copy() if "주문유형" in d.columns else d.iloc[0:0].copy()

    # AS / 교환 / 반품
    d_as = d[d["주문유형"].astype(str).eq("AS")].copy() if "주문유형" in d.columns else d.iloc[0:0].copy()
    d_exchange = (
        d_as[d_as["배송유형"].astype(str).eq("교환")].copy() if "배송유형" in d_as.columns else d_as.iloc[0:0].copy()
    )
    d_as_only = d_as.drop(index=d_exchange.index, errors="ignore")
    d_return = d[d["주문유형"].astype(str).str.contains("반품", na=False)].copy() if "주문유형" in d.columns else d.iloc[0:0].copy()

    # 월별 집계
    months = sorted(set(o["연월_키"].dropna().unique()).union(set(d["연월_키"].dropna().unique())))
    rows = []
    for m in months:
        denom = int(d_norm[d_norm["연월_키"] == m].shape[0])
        cancel = int(o_cancel[o_cancel["연월_키"] == m].shape[0])
        as_cnt = int(d_as_only[d_as_only["연월_키"] == m].shape[0])
        ex_cnt = int(d_exchange[d_exchange["연월_키"] == m].shape[0])
        ret_cnt = int(d_return[d_return["연월_키"] == m].shape[0])

        def rate(n: int, d_: int) -> float:
            return (n / d_) if d_ else 0.0

        rows.append(
            {
                "월": m,
                "정상(분모)": denom,
                "AS": as_cnt,
                "교환": ex_cnt,
                "반품": ret_cnt,
                "취소": cancel,
                "AS율": rate(as_cnt, denom),
                "교환율": rate(ex_cnt, denom),
                "반품율": rate(ret_cnt, denom),
                "취소율": rate(cancel, denom),
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        for c in ["AS율", "교환율", "반품율", "취소율"]:
            df[c] = (df[c] * 100).round(2)
    return df


def render(order_df: pd.DataFrame, delivery_df: pd.DataFrame, ctx: dict):
    st.subheader("📌 1.5 인사이트 (월별 KPI)")

    if order_df is None or delivery_df is None:
        st.info("데이터가 없어 KPI를 표시할 수 없습니다.")
        return

    cutoff = pd.Timestamp(ctx["yesterday"])
    kpi_df = _kpi_table(order_df, delivery_df, cutoff)
    if kpi_df.empty:
        st.info("KPI 계산에 필요한 날짜 컬럼(배송예정일)을 찾지 못했습니다.")
        return

    # 월 선택
    months = kpi_df["월"].tolist()
    default_idx = months.index(ctx["m_key"]) if ctx.get("m_key") in months else (len(months) - 1)
    sel_month = st.selectbox("월 선택", months, index=default_idx)

    # 표 출력(전체)
    show = kpi_df.copy()
    show = show.set_index("월")
    st.dataframe(
        show,
        width="stretch",
        hide_index=False,
    )

    # 선택 월 카드
    row = kpi_df[kpi_df["월"] == sel_month].iloc[0].to_dict()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("AS율(%)", f"{row['AS율']:.2f}", f"{row['AS']}건")
    c2.metric("교환율(%)", f"{row['교환율']:.2f}", f"{row['교환']}건")
    c3.metric("반품율(%)", f"{row['반품율']:.2f}", f"{row['반품']}건")
    c4.metric("취소율(%)", f"{row['취소율']:.2f}", f"{row['취소']}건")

    st.caption("분모는 정상(주문유형=정상) 기준이며, 날짜는 배송예정일 기준으로 기준일(어제)까지 집계합니다.")

