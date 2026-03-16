import pandas as pd


def valid_bucket_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out["버킷"] = out["최종상태"].astype(str)
    out.loc[(out["버킷"] == "정상") & ~(out.get("정상(상세)", 0) > 0), "버킷"] = "미분류"
    return out[out["버킷"].isin(["정상", "AS", "교환", "반품", "취소"])].copy()


def rank_cancel(base: pd.DataFrame, col: str) -> pd.DataFrame:
    if base is None or base.empty or col not in base.columns:
        return pd.DataFrame()
    g = (
        base.groupby(col, dropna=False)
        .agg(전체=("주문번호", "size"), 정상=("버킷", lambda x: int((x == "정상").sum())), 취소=("버킷", lambda x: int((x == "취소").sum())))
        .reset_index()
    )
    g["취소율(%)"] = (g["취소"] / g["전체"] * 100).round(2)
    return g.sort_values(["취소", "취소율(%)"], ascending=False)


def rank_return(base: pd.DataFrame, col: str) -> pd.DataFrame:
    if base is None or base.empty or col not in base.columns:
        return pd.DataFrame()
    g = (
        base.groupby(col, dropna=False)
        .agg(전체=("주문번호", "size"), 정상=("버킷", lambda x: int((x == "정상").sum())), 반품=("버킷", lambda x: int((x == "반품").sum())))
        .reset_index()
    )
    g["반품율(%)"] = (g["반품"] / g["전체"] * 100).round(2)
    return g.sort_values(["반품", "반품율(%)"], ascending=False)


def build_risk_top(o_m: pd.DataFrame, d_m: pd.DataFrame, top_n: int) -> pd.DataFrame:
    d_as = d_m[d_m.get("배송유형", "").astype(str).eq("AS")].copy() if "배송유형" in d_m.columns else d_m.iloc[0:0]
    d_exchange = d_m[d_m.get("배송유형", "").astype(str).eq("교환")].copy() if "배송유형" in d_m.columns else d_m.iloc[0:0]

    ret_mask = pd.Series(False, index=d_m.index)
    if "배송유형" in d_m.columns:
        ret_mask |= d_m["배송유형"].astype(str).isin(["반품", "회수"])
    if "주문유형" in d_m.columns:
        ret_mask |= d_m["주문유형"].astype(str).eq("반품")
    d_return = d_m[ret_mask].copy()
    d_cancel = d_m[d_m.get("배송상태", "").astype(str).eq("미설치")].copy() if "배송상태" in d_m.columns else d_m.iloc[0:0]

    def _counts(df: pd.DataFrame, label: str) -> pd.DataFrame:
        if df is None or df.empty or "주문번호" not in df.columns:
            return pd.DataFrame(columns=["주문번호", label])
        return df.groupby("주문번호", dropna=False).size().reset_index(name=label)

    risk = None
    for part in [_counts(d_as, "AS"), _counts(d_exchange, "교환"), _counts(d_return, "반품"), _counts(d_cancel, "취소")]:
        risk = part if risk is None else risk.merge(part, on="주문번호", how="outer")
    risk = risk.fillna(0)
    for col in ["AS", "교환", "반품", "취소"]:
        risk[col] = risk.get(col, 0).astype(int)

    name_map = {}
    if "주문번호" in o_m.columns and "수취인" in o_m.columns:
        name_map.update(
            o_m.dropna(subset=["주문번호"])
            .groupby("주문번호")["수취인"]
            .agg(lambda x: x.dropna().astype(str).iloc[0] if len(x.dropna()) else "")
            .to_dict()
        )
    if "주문번호" in d_m.columns and "수취인" in d_m.columns:
        name_map.update(
            d_m.dropna(subset=["주문번호"])
            .groupby("주문번호")["수취인"]
            .agg(lambda x: x.dropna().astype(str).iloc[0] if len(x.dropna()) else "")
            .to_dict()
        )

    risk["고객명"] = risk["주문번호"].map(name_map).fillna("")
    risk["주문번호 (고객명)"] = risk.apply(
        lambda r: f"{r['주문번호']} ({r['고객명']})" if str(r.get("고객명", "")).strip() else str(r["주문번호"]),
        axis=1,
    )
    risk["리스크점수"] = (risk["AS"] + risk["교환"] + risk["반품"]) * 2 + risk["취소"]
    risk = risk.sort_values(["리스크점수", "반품", "교환", "AS", "취소"], ascending=False)
    return risk.head(top_n)[["주문번호 (고객명)", "리스크점수", "AS", "교환", "반품", "취소"]].copy()

