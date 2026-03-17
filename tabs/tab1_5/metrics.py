import pandas as pd
import numpy as np
import streamlit as st
from services.domain_rules import cheongho_mask, filter_cheongho, delivery_event_flags


def safe_to_datetime(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")


def is_cheongho(df: pd.DataFrame) -> pd.Series:
    return cheongho_mask(df)


def show_table(df: pd.DataFrame, percent_cols=(), int_cols=()):
    view = df.copy().reset_index(drop=True)
    for c in percent_cols:
        if c in view.columns:
            s = pd.to_numeric(view[c], errors="coerce")
            view[c] = s.map(lambda x: f"{x:.2f}" if pd.notna(x) else "")
    for c in int_cols:
        if c in view.columns:
            s = pd.to_numeric(view[c], errors="coerce")
            view[c] = s.map(lambda x: f"{x:,.0f}" if pd.notna(x) else "")
    st.dataframe(view, hide_index=True, use_container_width=True)


def month_key(d: pd.Series) -> pd.Series:
    return d.dt.strftime("%Y-%m")


def seller_branch_map_from_order(order_df: pd.DataFrame) -> pd.DataFrame:
    if order_df is None or order_df.empty or "주문번호" not in order_df.columns:
        return pd.DataFrame(columns=["주문번호", "판매인", "판매지국"])
    o = filter_cheongho(order_df.copy())
    cols = [c for c in ["주문번호", "판매인", "판매지국"] if c in o.columns]
    if "주문번호" not in cols:
        return pd.DataFrame(columns=["주문번호", "판매인", "판매지국"])
    for c in ["판매인", "판매지국"]:
        if c not in cols:
            o[c] = ""
            cols.append(c)
    s = o[cols].dropna(subset=["주문번호"]).copy()
    for c in ["판매인", "판매지국"]:
        s[c] = s[c].replace("", pd.NA)
    out = s.groupby("주문번호", dropna=False)[["판매인", "판매지국"]].first().reset_index()
    out["판매인"] = out["판매인"].fillna("")
    out["판매지국"] = out["판매지국"].fillna("")
    return out


@st.cache_data(ttl=300, show_spinner=False)
def build_event_seller_summary(order_df: pd.DataFrame, delivery_df: pd.DataFrame, month_key_value: str) -> pd.DataFrame:
    if delivery_df is None or delivery_df.empty or "주문번호" not in delivery_df.columns:
        return pd.DataFrame()

    d = filter_cheongho(delivery_df.copy())
    if "배송예정일" not in d.columns:
        return pd.DataFrame()

    d["연월_키"] = month_key(safe_to_datetime(d["배송예정일"]))
    d = d[d["연월_키"].eq(month_key_value)].copy()
    if d.empty:
        return pd.DataFrame()

    map_df = seller_branch_map_from_order(order_df)
    d = d.merge(map_df, on="주문번호", how="left")
    flags = delivery_event_flags(d)

    key_cols = ["주문번호", "판매인", "판매지국"]
    dm = d[key_cols].copy()
    dm["정상완료_evt"] = flags["is_normal_complete"].astype(int)
    dm["취소_evt"] = flags["is_cancel"].astype(int)
    dm["반품_evt"] = flags["is_return"].astype(int)
    dm["AS_evt"] = flags["is_as"].astype(int)
    dm["교환_evt"] = flags["is_exchange"].astype(int)

    by_order = (
        dm.groupby(key_cols, dropna=False)[["정상완료_evt", "취소_evt", "반품_evt", "AS_evt", "교환_evt"]]
        .max()
        .reset_index()
    )
    out = (
        by_order.groupby("판매인", dropna=False)
        .agg(
            이벤트_전체=("주문번호", "size"),
            정상완료=("정상완료_evt", "sum"),
            취소=("취소_evt", "sum"),
            반품=("반품_evt", "sum"),
            AS=("AS_evt", "sum"),
            교환=("교환_evt", "sum"),
        )
        .reset_index()
    )
    seller_to_branch = (
        by_order.groupby("판매인")["판매지국"]
        .agg(lambda x: x.dropna().astype(str).mode().iloc[0] if len(x.dropna()) else "")
        .to_dict()
    )
    out["판매지국"] = out["판매인"].map(seller_to_branch).fillna("")
    out["이벤트_취소율(%)"] = (out["취소"] / out["이벤트_전체"] * 100).fillna(0).round(2)
    out["이벤트_반품율(%)"] = (out["반품"] / out["이벤트_전체"] * 100).fillna(0).round(2)
    return out.sort_values(["반품", "취소", "이벤트_전체"], ascending=False)


@st.cache_data(ttl=300, show_spinner=False)
def build_r14_summary(order_df: pd.DataFrame, delivery_df: pd.DataFrame) -> pd.DataFrame:
    if delivery_df is None or delivery_df.empty or "주문번호" not in delivery_df.columns:
        return pd.DataFrame()

    d = filter_cheongho(delivery_df.copy())
    if d.empty:
        return pd.DataFrame()

    if "배송예정일" not in d.columns:
        return pd.DataFrame()
    reg_col = None
    for c in ["등록일", "주문등록일", "완료시간"]:
        if c in d.columns:
            reg_col = c
            break

    d["배송예정일_DT"] = safe_to_datetime(d["배송예정일"])
    d["등록일_DT"] = safe_to_datetime(d[reg_col]) if reg_col else pd.NaT

    d = d.merge(seller_branch_map_from_order(order_df), on="주문번호", how="left")
    if "주문번호" not in d.columns:
        return pd.DataFrame()

    flags = delivery_event_flags(d)
    normal_complete = flags["is_normal_complete"] & d["배송예정일_DT"].notna()
    is_return = flags["is_return"]

    comp = d.loc[normal_complete, ["주문번호", "배송예정일_DT", "판매인", "판매지국"]].copy()
    if comp.empty:
        return pd.DataFrame()
    comp = comp.sort_values(["주문번호", "배송예정일_DT"])
    comp_first = (
        comp.groupby("주문번호", dropna=False)
        .agg(정상완료일=("배송예정일_DT", "min"), 판매인=("판매인", "first"), 판매지국=("판매지국", "first"))
        .reset_index()
    )
    comp_first["판매인"] = comp_first["판매인"].fillna("")
    comp_first["판매지국"] = comp_first["판매지국"].fillna("")
    comp_first["코호트월"] = comp_first["정상완료일"].dt.strftime("%Y-%m")

    ret = d[is_return & d["등록일_DT"].notna()].copy()
    if ret.empty:
        out = comp_first.copy()
        out["반품등록일"] = pd.NaT
        out["반품소요일"] = pd.NA
        out["R14"] = 0
        out["R7"] = 0
        return out

    ret_first = ret.sort_values("등록일_DT").groupby("주문번호", dropna=False)["등록일_DT"].min().reset_index(name="반품등록일")
    out = comp_first.merge(ret_first, on="주문번호", how="left")
    out["반품소요일"] = (out["반품등록일"] - out["정상완료일"]).dt.days
    out["R14"] = ((out["반품소요일"] >= 0) & (out["반품소요일"] <= 14)).astype(int)
    out["R7"] = ((out["반품소요일"] >= 0) & (out["반품소요일"] <= 7)).astype(int)
    return out


@st.cache_data(ttl=300, show_spinner=False)
def build_order_month_summary(order_df: pd.DataFrame, delivery_df: pd.DataFrame) -> pd.DataFrame:
    if delivery_df is None or delivery_df.empty or "주문번호" not in delivery_df.columns:
        return pd.DataFrame()

    d = filter_cheongho(delivery_df.copy())
    if "배송예정일" not in d.columns:
        return pd.DataFrame()

    d["연월_키"] = month_key(safe_to_datetime(d["배송예정일"]))
    d = d[d["연월_키"].notna()].copy()
    if d.empty:
        return pd.DataFrame()

    flags = delivery_event_flags(d)
    by_order_month = (
        d.assign(
            _cancel=flags["is_cancel"].astype(int),
            _exchange=flags["is_exchange"].astype(int),
            _as=flags["is_as"].astype(int),
            _return=flags["is_return"].astype(int),
            _normal=flags["is_normal_strict"].astype(int),
        )
        .groupby(["연월_키", "주문번호"], dropna=False)[["_cancel", "_exchange", "_as", "_return", "_normal"]]
        .max()
        .reset_index()
        .rename(columns={"_cancel": "취소발생", "_exchange": "교환발생", "_as": "AS발생", "_return": "반품발생", "_normal": "정상(상세)"})
    )

    conds = [
        by_order_month["반품발생"] > 0,
        by_order_month["교환발생"] > 0,
        by_order_month["AS발생"] > 0,
        by_order_month["정상(상세)"] > 0,
        by_order_month["취소발생"] > 0,
    ]
    by_order_month["최종상태"] = np.select(conds, ["반품", "교환", "AS", "정상", "취소"], default="정상")

    o = order_df.copy() if order_df is not None else pd.DataFrame()
    if not o.empty and "주문번호" in o.columns:
        o = filter_cheongho(o)
        cols = [c for c in ["주문번호", "판매인", "판매지국", "수취인", "상품코드", "상품명", "등록일"] if c in o.columns]
        if cols:
            src = o[cols].dropna(subset=["주문번호"]).copy()
            if "등록일" in src.columns:
                src["_등록일_dt"] = pd.to_datetime(src["등록일"], errors="coerce")
                src = src.sort_values(["주문번호", "_등록일_dt"], na_position="last")
            else:
                src = src.sort_values(["주문번호"])

            for c in [c for c in cols if c not in ("주문번호", "등록일")]:
                src[c] = src[c].replace("", pd.NA)

            agg_map = {c: "first" for c in cols if c not in ("주문번호", "등록일")}
            if "등록일" in cols:
                agg_map["등록일"] = "min"

            base = src.groupby("주문번호", dropna=False).agg(agg_map).reset_index()
            for c in [c for c in agg_map if c != "등록일"]:
                base[c] = base[c].fillna("")
            by_order_month = by_order_month.merge(base, on="주문번호", how="left")

    return by_order_month


def kpi_table(delivery_df: pd.DataFrame) -> pd.DataFrame:
    om = build_order_month_summary(pd.DataFrame(), delivery_df)
    if om.empty:
        return pd.DataFrame()

    bucket = pd.Series("미분류", index=om.index)
    bucket[om["최종상태"].astype(str).eq("취소")] = "취소"
    bucket[(bucket == "미분류") & om["최종상태"].astype(str).eq("반품")] = "반품"
    bucket[(bucket == "미분류") & om["최종상태"].astype(str).eq("교환")] = "교환"
    bucket[(bucket == "미분류") & om["최종상태"].astype(str).eq("AS")] = "AS"
    bucket[(bucket == "미분류") & om["최종상태"].astype(str).eq("정상") & (om["정상(상세)"] > 0)] = "정상"
    om["버킷"] = bucket

    rows = []
    for m in sorted(set(om["연월_키"].dropna().unique())):
        dm = om[om["연월_키"] == m]
        ok_cnt = int((dm["버킷"] == "정상").sum())
        as_cnt = int((dm["버킷"] == "AS").sum())
        ex_cnt = int((dm["버킷"] == "교환").sum())
        ret_cnt = int((dm["버킷"] == "반품").sum())
        cancel = int((dm["버킷"] == "취소").sum())
        unclassified = int((dm["버킷"] == "미분류").sum())
        denom = ok_cnt + as_cnt + ex_cnt + ret_cnt + cancel

        def rate(n: int, d_: int) -> float:
            return (n / d_) if d_ else 0.0

        rows.append(
            {
                "월": m,
                "전체": denom,
                "정상": ok_cnt,
                "AS": as_cnt,
                "교환": ex_cnt,
                "반품": ret_cnt,
                "취소": cancel,
                "미분류": unclassified,
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
