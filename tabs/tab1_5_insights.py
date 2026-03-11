# tabs/tab1_5_insights.py
# 1.5 인사이트 (월별 AS/교환/반품/취소율)

import pandas as pd
import streamlit as st


def _safe_to_datetime(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")

def _center_style(df: pd.DataFrame):
    return (
        df.style.set_properties(**{"text-align": "center"})
        .set_table_styles([{"selector": "th", "props": [("text-align", "center")]}])
    )


def _month_key(d: pd.Series) -> pd.Series:
    return d.dt.strftime("%Y-%m")


def _kpi_table(order_df: pd.DataFrame, delivery_df: pd.DataFrame) -> pd.DataFrame:
    """
    - 날짜 기준: 배송예정일
    - 교환: 주문유형='AS' AND 배송유형='교환'
    - 전체(분모): 주문유형='정상' (정상 유형 전체)
    - 정상: 아래 기준 충족
      1) 주문유형 : 정상
      2) 주문상태 : 주문취소 빼고 다
      3) 배송유형 : 정상
      4) 배송상태 : 미설치 빼고 다
    """

    # --- 주문(취소율) ---
    o = order_df.copy()
    o_dt = _safe_to_datetime(o["배송예정일"]) if "배송예정일" in o.columns else pd.Series([], dtype="datetime64[ns]")
    if not o_dt.notna().any():
        return pd.DataFrame()
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
    d["연월_키"] = _month_key(d_dt)

    # 전체(분모): 정상 유형 전체 (주문유형=정상)
    d_total = d[d["주문유형"].astype(str).str.contains("정상", na=False)].copy() if "주문유형" in d.columns else d.iloc[0:0].copy()

    # 정상: 상세 조건 충족
    d_ok = d_total.copy()
    if "주문상태" in d_ok.columns:
        d_ok = d_ok[~d_ok["주문상태"].astype(str).eq("주문취소")].copy()
    if "배송유형" in d_ok.columns:
        d_ok = d_ok[d_ok["배송유형"].astype(str).eq("정상")].copy()
    if "배송상태" in d_ok.columns:
        d_ok = d_ok[~d_ok["배송상태"].astype(str).eq("미설치")].copy()

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
        denom = int(d_total[d_total["연월_키"] == m].shape[0])
        ok_cnt = int(d_ok[d_ok["연월_키"] == m].shape[0])
        cancel = int(o_cancel[o_cancel["연월_키"] == m].shape[0])
        as_cnt = int(d_as_only[d_as_only["연월_키"] == m].shape[0])
        ex_cnt = int(d_exchange[d_exchange["연월_키"] == m].shape[0])
        ret_cnt = int(d_return[d_return["연월_키"] == m].shape[0])

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
    st.subheader("📌 1.5 인사이트")

    # Streamlit의 st.dataframe은 Styler의 정렬이 환경/버전별로 무시될 수 있어 CSS로 강제 중앙정렬합니다.
    st.markdown(
        """
<style>
div[data-testid="stDataFrame"] th, div[data-testid="stDataFrame"] td {
  text-align: center !important;
}
</style>
""",
        unsafe_allow_html=True,
    )

    if order_df is None or delivery_df is None:
        st.info("데이터가 없어 KPI를 표시할 수 없습니다.")
        return

    kpi_df = _kpi_table(order_df, delivery_df)
    if kpi_df.empty:
        st.info("KPI 계산에 필요한 날짜 컬럼(배송예정일)을 찾지 못했습니다.")
        return

    st.subheader("비정상 주문 분석")

    # 월 선택
    months = kpi_df["월"].tolist()
    default_idx = months.index(ctx["m_key"]) if ctx.get("m_key") in months else (len(months) - 1)
    sel_month = st.selectbox("월 선택", months, index=default_idx)

    # 선택 월 카드(표 위)
    row = kpi_df[kpi_df["월"] == sel_month].iloc[0].to_dict()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("AS율(%)", f"{row['AS율']:.2f}", f"{row['AS']}건")
    c2.metric("교환율(%)", f"{row['교환율']:.2f}", f"{row['교환']}건")
    c3.metric("반품율(%)", f"{row['반품율']:.2f}", f"{row['반품']}건")
    c4.metric("취소율(%)", f"{row['취소율']:.2f}", f"{row['취소']}건")

    st.subheader("월별 비정상 유형별 분석")

    # 표 출력(전체)
    show = kpi_df.copy()
    show = show.set_index("월")
    show = show.rename(
        columns={
            "AS율": "AS율(%)",
            "교환율": "교환율(%)",
            "반품율": "반품율(%)",
            "취소율": "취소율(%)",
        }
    )
    st.dataframe(
        _center_style(show).format({c: "{:.2f}" for c in ["AS율(%)", "교환율(%)", "반품율(%)", "취소율(%)"] if c in show.columns}),
        width="stretch",
        hide_index=False,
    )

    st.caption("날짜는 배송예정일 기준으로 집계합니다. '전체'는 정상(주문유형=정상) 유형 전체, '정상'은 상세 기준을 충족한 건입니다.")

    # ==========================
    # 의사결정용 표시 (드릴다운)
    # ==========================

    st.divider()
    st.subheader("🧭 의사결정용 표시")

    # 공통: 선택 월 데이터 슬라이스 (배송예정일 기준, 기준일(어제)까지)
    o = order_df.copy()
    if "배송예정일" in o.columns:
        o_dt = _safe_to_datetime(o["배송예정일"])
        o["연월_키"] = _month_key(o_dt)
    else:
        o = o.iloc[0:0].copy()

    d = delivery_df.copy()
    if "배송예정일" in d.columns:
        d_dt = _safe_to_datetime(d["배송예정일"])
        d["연월_키"] = _month_key(d_dt)
    else:
        d = d.iloc[0:0].copy()

    o_m = o[o.get("연월_키", "") == sel_month].copy()
    d_m = d[d.get("연월_키", "") == sel_month].copy()

    # 1) 리스크 TOP 주문번호 리스트
    with st.expander("1) 리스크 TOP 주문번호 (AS/교환/반품/취소)", expanded=True):
        required = {"주문번호"}
        if not required.issubset(set(o_m.columns).union(set(d_m.columns))):
            st.info("주문번호 컬럼이 없어 표시할 수 없습니다.")
        else:
            # 분모(정상) 기준: 정상 주문에서 파생된 이슈를 주문번호 단위로 집계
            d_as = d_m[d_m.get("주문유형", "").astype(str).eq("AS")].copy() if "주문유형" in d_m.columns else d_m.iloc[0:0]
            d_exchange = (
                d_as[d_as.get("배송유형", "").astype(str).eq("교환")].copy() if "배송유형" in d_as.columns else d_as.iloc[0:0]
            )
            d_as_only = d_as.drop(index=d_exchange.index, errors="ignore")
            d_return = d_m[d_m.get("주문유형", "").astype(str).str.contains("반품", na=False)].copy() if "주문유형" in d_m.columns else d_m.iloc[0:0]

            o_norm = o_m[o_m.get("주문유형", "").astype(str).eq("정상")].copy() if "주문유형" in o_m.columns else o_m.iloc[0:0]
            o_cancel = (
                o_norm[o_norm.get("주문상태", "").astype(str).eq("주문취소")].copy() if "주문상태" in o_norm.columns else o_norm.iloc[0:0]
            )

            def _counts(df: pd.DataFrame, label: str) -> pd.DataFrame:
                if df is None or df.empty or "주문번호" not in df.columns:
                    return pd.DataFrame(columns=["주문번호", label])
                return df.groupby("주문번호", dropna=False).size().reset_index(name=label)

            c_as = _counts(d_as_only, "AS")
            c_ex = _counts(d_exchange, "교환")
            c_ret = _counts(d_return, "반품")
            c_can = _counts(o_cancel, "취소")

            risk = None
            for part in [c_as, c_ex, c_ret, c_can]:
                risk = part if risk is None else risk.merge(part, on="주문번호", how="outer")
            risk = risk.fillna(0)
            for col in ["AS", "교환", "반품", "취소"]:
                if col in risk.columns:
                    risk[col] = risk[col].astype(int)
                else:
                    risk[col] = 0

            # 고객명 매핑 (order 우선, 없으면 delivery)
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

            # 단순 스코어: AS/교환/반품은 2점, 취소는 1점 (원하면 나중에 조정)
            risk["리스크점수"] = (risk["AS"] + risk["교환"] + risk["반품"]) * 2 + risk["취소"] * 1
            risk = risk.sort_values(["리스크점수", "반품", "교환", "AS", "취소"], ascending=False)

            top_n = st.slider("표시 개수", 5, 50, 15, key="risk_top_n")
            out = risk.head(top_n).copy()
            if out.empty:
                st.info("해당 월에 리스크 이벤트가 없습니다.")
            else:
                view = out[["주문번호 (고객명)", "리스크점수", "AS", "교환", "반품", "취소"]].copy()
                st.dataframe(_center_style(view), width="stretch", hide_index=True)

    # 2) AS/교환 급증 상품코드
    with st.expander("2) AS/교환 급증 상품코드 (전월 대비)", expanded=True):
        if "상품코드" not in d.columns or "주문유형" not in d.columns:
            st.info("상품코드/주문유형 컬럼이 없어 표시할 수 없습니다.")
        else:
            months_sorted = sorted(d["연월_키"].dropna().unique().tolist())
            prev_month = None
            if sel_month in months_sorted:
                idx = months_sorted.index(sel_month)
                prev_month = months_sorted[idx - 1] if idx > 0 else None

            if prev_month is None:
                st.info("전월 데이터가 없어 급증 비교를 할 수 없습니다.")
            else:
                d_prev = d[d["연월_키"] == prev_month].copy()

                def _issue_counts(df: pd.DataFrame) -> pd.DataFrame:
                    as_df = df[df["주문유형"].astype(str).eq("AS")].copy()
                    ex_df = as_df[as_df.get("배송유형", "").astype(str).eq("교환")].copy() if "배송유형" in as_df.columns else as_df.iloc[0:0]
                    as_only = as_df.drop(index=ex_df.index, errors="ignore")

                    as_c = as_only.groupby("상품코드").size().rename("AS").reset_index()
                    ex_c = ex_df.groupby("상품코드").size().rename("교환").reset_index()
                    out = as_c.merge(ex_c, on="상품코드", how="outer").fillna(0)
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

                min_cur = st.number_input("이번달 최소 이슈건수", min_value=1, max_value=9999, value=3, step=1, key="min_cur_issues")
                cand = merged[(merged["총이슈_이번달"] >= int(min_cur)) & (merged["증가"] > 0)].copy()
                cand = cand.sort_values(["증가", "총이슈_이번달"], ascending=False)

                if cand.empty:
                    st.info("전월 대비 급증한 상품코드가 없습니다.")
                else:
                    # 상품명 매핑 (이번달 우선)
                    name_df = d_m.copy()
                    if "상품코드" in name_df.columns and "상품명" in name_df.columns:
                        code_to_name = (
                            name_df.dropna(subset=["상품코드"])
                            .groupby("상품코드")["상품명"]
                            .agg(lambda x: x.dropna().astype(str).mode().iloc[0] if len(x.dropna()) else "")
                            .to_dict()
                        )
                    else:
                        code_to_name = {}

                    view = cand.head(30).copy()
                    view["상품명"] = view["상품코드"].map(code_to_name).fillna("")
                    view["상품코드 (상품명)"] = view.apply(
                        lambda r: f"{r['상품코드']} ({r['상품명']})" if str(r.get('상품명','')).strip() else str(r["상품코드"]),
                        axis=1,
                    )
                    view = view[
                        [
                            "상품코드 (상품명)",
                            "증가",
                            "총이슈_이번달",
                            "총이슈_전월",
                            "AS_이번달",
                            "교환_이번달",
                            "AS_전월",
                            "교환_전월",
                        ]
                    ].copy()
                    view = view.rename(
                        columns={
                            "총이슈_이번달": "총이슈(이번달)",
                            "총이슈_전월": "총이슈(전월)",
                            "AS_이번달": "AS(이번달)",
                            "교환_이번달": "교환(이번달)",
                            "AS_전월": "AS(전월)",
                            "교환_전월": "교환(전월)",
                        }
                    )
                    st.dataframe(_center_style(view), width="stretch", hide_index=True)

    # 3) 취소율 높은 판매지국/판매인
    with st.expander("3) 취소율 높은 판매지국/판매인 (정상 분모 기준)", expanded=True):
        if o_m.empty or "주문유형" not in o_m.columns or "주문상태" not in o_m.columns:
            st.info("주문유형/주문상태 컬럼이 없어 표시할 수 없습니다.")
        else:
            norm = o_m[o_m["주문유형"].astype(str).eq("정상")].copy()
            if norm.empty:
                st.info("해당 월에 정상 주문이 없습니다.")
            else:
                norm["is_cancel"] = norm["주문상태"].astype(str).eq("주문취소")

                def _rate_by(col: str) -> pd.DataFrame:
                    if col not in norm.columns:
                        return pd.DataFrame()
                    g = norm.groupby(col, dropna=False).agg(정상=("is_cancel", "size"), 취소=("is_cancel", "sum")).reset_index()
                    g["취소율(%)"] = (g["취소"] / g["정상"] * 100).round(2)
                    return g.sort_values(["취소율(%)", "취소"], ascending=False)

                min_denom = st.number_input("최소 정상건수(필터)", min_value=1, max_value=99999, value=30, step=1, key="min_cancel_denom")

                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**판매지국 TOP**")
                    g = _rate_by("판매지국")
                    if g.empty:
                        st.info("판매지국 컬럼이 없습니다.")
                    else:
                        st.dataframe(g[g["정상"] >= int(min_denom)].head(20), width="stretch", hide_index=True)
                with c2:
                    st.markdown("**판매인 TOP**")
                    g = _rate_by("판매인")
                    if g.empty:
                        st.info("판매인 컬럼이 없습니다.")
                    else:
                        view = g[g["정상"] >= int(min_denom)].copy()
                        if "판매지국" in norm.columns:
                            seller_to_branch = (
                                norm.dropna(subset=["판매인"])
                                .groupby("판매인")["판매지국"]
                                .agg(lambda x: x.dropna().astype(str).mode().iloc[0] if len(x.dropna()) else "")
                                .to_dict()
                            )
                            view["판매지국"] = view["판매인"].map(seller_to_branch).fillna("")
                            view["판매인 (판매지국)"] = view.apply(
                                lambda r: f"{r['판매인']} ({r['판매지국']})" if str(r.get('판매지국','')).strip() else str(r["판매인"]),
                                axis=1,
                            )
                            view = view[["판매인 (판매지국)", "정상", "취소", "취소율(%)"]]
                        else:
                            view = view[["판매인", "정상", "취소", "취소율(%)"]]
                        st.dataframe(_center_style(view.head(20)), width="stretch", hide_index=True)
