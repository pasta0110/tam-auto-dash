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


def add_seller_branch_label(
    df: pd.DataFrame,
    seller_col: str = "판매인",
    branch_col: str = "판매지국",
    out_col: str = "판매인 (판매지국)",
) -> pd.DataFrame:
    if df is None or df.empty or seller_col not in df.columns:
        return pd.DataFrame() if df is None else df.copy()
    out = df.copy()
    if branch_col not in out.columns:
        out[branch_col] = ""
    out[seller_col] = out[seller_col].astype(str).fillna("")
    out[branch_col] = out[branch_col].astype(str).fillna("")
    out[out_col] = out.apply(
        lambda r: f"{r[seller_col]} ({r[branch_col]})" if str(r.get(branch_col, "")).strip() else str(r[seller_col]),
        axis=1,
    )
    return out


def build_issue_spike_view(d_m: pd.DataFrame, d_prev: pd.DataFrame, top_n: int = 30) -> pd.DataFrame:
    if d_m is None or d_prev is None:
        return pd.DataFrame()
    required = {"상품코드", "배송유형"}
    if not required.issubset(set(d_m.columns)) or not required.issubset(set(d_prev.columns)):
        return pd.DataFrame()

    def _issue_counts(df: pd.DataFrame) -> pd.DataFrame:
        as_df = df[df["배송유형"].astype(str).eq("AS")].copy()
        ex_df = df[df["배송유형"].astype(str).eq("교환")].copy()
        out = (
            as_df.groupby("상품코드").size().rename("AS").reset_index().merge(
                ex_df.groupby("상품코드").size().rename("교환").reset_index(),
                on="상품코드",
                how="outer",
            )
        ).fillna(0)
        out["AS"] = out["AS"].astype(int)
        out["교환"] = out["교환"].astype(int)
        out["총이슈"] = out["AS"] + out["교환"]
        return out

    cur = _issue_counts(d_m)
    prev = _issue_counts(d_prev)
    merged = cur.merge(prev, on="상품코드", how="outer", suffixes=("_이번달", "_전월")).fillna(0)
    for c in ["AS_이번달", "교환_이번달", "총이슈_이번달", "AS_전월", "교환_전월", "총이슈_전월"]:
        merged[c] = merged[c].astype(int)
    merged["증가"] = merged["총이슈_이번달"] - merged["총이슈_전월"]
    cand = merged[(merged["총이슈_이번달"] > 0) & (merged["증가"] > 0)].copy().sort_values(
        ["증가", "총이슈_이번달"], ascending=False
    )
    if cand.empty:
        return pd.DataFrame()

    code_to_name = {}
    if "상품명" in d_m.columns:
        name_df = d_m.dropna(subset=["상품코드"]).copy()
        if not name_df.empty:
            code_to_name = name_df.groupby("상품코드")["상품명"].first().fillna("").to_dict()

    view = cand.head(top_n).copy()
    view["상품명"] = view["상품코드"].map(code_to_name).fillna("")
    view["상품코드 (상품명)"] = view.apply(
        lambda r: f"{r['상품코드']} ({r['상품명']})" if str(r.get("상품명", "")).strip() else str(r["상품코드"]),
        axis=1,
    )
    return view[
        ["상품코드 (상품명)", "증가", "총이슈_이번달", "총이슈_전월", "AS_이번달", "교환_이번달", "AS_전월", "교환_전월"]
    ].rename(
        columns={
            "총이슈_이번달": "총이슈(이번달)",
            "총이슈_전월": "총이슈(전월)",
            "AS_이번달": "AS(이번달)",
            "교환_이번달": "교환(이번달)",
            "AS_전월": "AS(전월)",
            "교환_전월": "교환(전월)",
        }
    )


def build_r14_seller_summary(r14_m: pd.DataFrame) -> pd.DataFrame:
    if r14_m is None or r14_m.empty or "판매인" not in r14_m.columns:
        return pd.DataFrame()
    s = (
        r14_m.groupby("판매인", dropna=False)
        .agg(정상완료=("주문번호", "size"), R14=("R14", "sum"), R7=("R7", "sum"))
        .reset_index()
    )
    s["판매인"] = s["판매인"].astype(str).fillna("").str.strip()
    s = s[s["판매인"] != ""].copy()
    if s.empty:
        return pd.DataFrame()
    if "판매지국" in r14_m.columns:
        seller_to_branch = r14_m.groupby("판매인")["판매지국"].first().fillna("").to_dict()
        s["판매지국"] = s["판매인"].map(seller_to_branch).fillna("")
    s["R14율(%)"] = (s["R14"] / s["정상완료"] * 100).fillna(0).round(2)
    s["R7율(%)"] = (s["R7"] / s["정상완료"] * 100).fillna(0).round(2)
    s["의심점수"] = ((s["R14율(%)"] >= 15).astype(int) * 2 + (s["R14"] >= 5).astype(int) * 2 + (s["R7율(%)"] >= 10).astype(int))
    s = s.sort_values(["의심점수", "R14율(%)", "R14", "정상완료"], ascending=False)
    return add_seller_branch_label(s, seller_col="판매인", branch_col="판매지국", out_col="판매인 (판매지국)")


def build_r14_seller_trend(r14: pd.DataFrame, seller: str) -> pd.DataFrame:
    if r14 is None or r14.empty or "판매인" not in r14.columns or not seller:
        return pd.DataFrame()
    t = r14[r14["판매인"].astype(str).eq(str(seller))].copy()
    if t.empty:
        return pd.DataFrame()
    trend = (
        t.groupby("코호트월", dropna=False)
        .agg(정상완료=("주문번호", "size"), R14=("R14", "sum"), R7=("R7", "sum"))
        .reset_index()
        .sort_values("코호트월")
    )
    trend["R14율(%)"] = (trend["R14"] / trend["정상완료"] * 100).fillna(0).round(2)
    trend["R7율(%)"] = (trend["R7"] / trend["정상완료"] * 100).fillna(0).round(2)
    return trend
