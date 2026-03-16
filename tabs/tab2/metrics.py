import pandas as pd
import streamlit as st


REQUIRED_COLS = {"연월_키", "배송사_정제", "주문유형", "배송상태", "매출처"}


@st.cache_data(ttl=300, show_spinner=False)
def prepare_work_df(ana_df: pd.DataFrame) -> pd.DataFrame:
    if ana_df is None or ana_df.empty:
        return pd.DataFrame()

    missing_cols = [c for c in REQUIRED_COLS if c not in ana_df.columns]
    if missing_cols:
        return pd.DataFrame()

    work_df = ana_df.copy()
    work_df = work_df[work_df["매출처"].astype(str).str.strip().eq("청호나이스")].copy()
    if work_df.empty:
        return pd.DataFrame()

    month_dt = pd.to_datetime(work_df["연월_키"].astype(str) + "-01", errors="coerce")
    work_df = work_df.loc[month_dt.notna()].copy()
    work_df["월일자"] = month_dt.loc[month_dt.notna()]
    work_df["연월_키"] = work_df["월일자"].dt.strftime("%Y-%m")
    return work_df


@st.cache_data(ttl=300, show_spinner=False)
def build_total_compare(work_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    if work_df is None or work_df.empty:
        return pd.DataFrame(), []

    total_compare = (
        work_df.groupby(["연월_키", "월일자", "배송사_정제"], as_index=False)
        .size()
        .rename(columns={"배송사_정제": "지역센터", "size": "완료건수"})
    )
    all_months = (
        total_compare[["연월_키", "월일자"]]
        .drop_duplicates()
        .sort_values("월일자")["연월_키"]
        .tolist()
    )
    return total_compare, all_months


def bar_view_data(total_compare: pd.DataFrame, view_months: list[str]):
    if total_compare is None or total_compare.empty or not view_months:
        return pd.DataFrame(), pd.Series(dtype="int64"), []

    df_view = total_compare[total_compare["연월_키"].isin(view_months)].copy()
    monthly_totals = df_view.groupby("연월_키")["완료건수"].sum()
    month_labels = [f"{m}<br>[총 합계: {int(monthly_totals.get(m, 0)):,}건]" for m in view_months]
    return df_view, monthly_totals, month_labels


@st.cache_data(ttl=300, show_spinner=False)
def dual_axis_data(work_df: pd.DataFrame, center: str) -> pd.DataFrame:
    if work_df is None or work_df.empty:
        return pd.DataFrame()

    total_monthly = work_df.groupby("연월_키").size().reset_index(name="전체건수")
    v_monthly = work_df[work_df["배송사_정제"] == center].groupby("연월_키").size().reset_index(name="지역건수")
    df_combined = pd.merge(total_monthly, v_monthly, on="연월_키", how="left").fillna(0).sort_values("연월_키")
    df_combined["월일자"] = pd.to_datetime(df_combined["연월_키"] + "-01", errors="coerce")
    df_combined = df_combined.dropna(subset=["월일자"]).copy()
    return df_combined
