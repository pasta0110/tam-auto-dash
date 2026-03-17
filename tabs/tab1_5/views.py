import pandas as pd
import streamlit as st
from services.aggregations import (
    add_seller_branch_label,
    build_issue_spike_view,
    build_r14_seller_summary,
    build_r14_seller_trend,
)

from .metrics import (
    safe_to_datetime,
    month_key,
    show_table,
    kpi_table,
    build_order_month_summary,
    build_event_seller_summary,
    build_r14_summary,
)
from .risk import valid_bucket_df, rank_cancel, rank_return, build_risk_top


def render(order_df: pd.DataFrame, delivery_df: pd.DataFrame, ctx: dict):
    st.subheader("📌 1.5 인사이트")
    st.markdown(
        """
        <style>
        [data-testid="stDataFrame"] td div { text-align: center !important; }
        [data-testid="stDataFrame"] th div { text-align: center !important; }
        [data-testid="stTable"] td { text-align: center !important; }
        [data-testid="stTable"] th { text-align: center !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if order_df is None or delivery_df is None:
        st.info("데이터가 없어 KPI를 표시할 수 없습니다.")
        return

    kpi_df = kpi_table(delivery_df)
    if kpi_df.empty:
        st.info("KPI 계산에 필요한 날짜 컬럼(배송예정일)을 찾지 못했습니다.")
        return

    st.subheader("비정상 주문 분석")
    months = kpi_df["월"].tolist()
    default_idx = months.index(ctx["m_key"]) if ctx.get("m_key") in months else (len(months) - 1)
    sel_month = st.selectbox("월 선택", months, index=default_idx)

    row = kpi_df[kpi_df["월"] == sel_month].iloc[0].to_dict()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("AS율(%)", f"{row['AS율']:.2f}", f"{row['AS']}건(주문)")
    c2.metric("교환율(%)", f"{row['교환율']:.2f}", f"{row['교환']}건(주문)")
    c3.metric("반품율(%)", f"{row['반품율']:.2f}", f"{row['반품']}건(주문)")
    c4.metric("취소율(%)", f"{row['취소율']:.2f}", f"{row['취소']}건(주문)")

    st.subheader("월별 비정상 유형별 분석")
    show = kpi_df.copy()
    unclassified_total = int(show["미분류"].sum()) if "미분류" in show.columns else 0
    if "미분류" in show.columns:
        show = show.drop(columns=["미분류"])
    show = show.rename(columns={"AS율": "AS율(%)", "교환율": "교환율(%)", "반품율": "반품율(%)", "취소율": "취소율(%)"})
    show_table(show, percent_cols=["AS율(%)", "교환율(%)", "반품율(%)", "취소율(%)"], int_cols=["전체", "정상", "AS", "교환", "반품", "취소"])
    if unclassified_total:
        st.warning(f"⚠️ 미분류 데이터가 {unclassified_total}건 있습니다. (전체 합계에는 포함되지 않음)")

    st.caption("날짜는 배송예정일 기준, 집계 단위는 '주문번호'입니다. '전체'는 5개 버킷(정상/AS/교환/반품/취소)의 합이며 '정상'은 상세 기준을 충족한 주문만 포함합니다.")

    st.divider()
    st.subheader("🧭 의사결정용 표시")

    o = order_df.copy()
    if "배송예정일" in o.columns:
        o["연월_키"] = month_key(safe_to_datetime(o["배송예정일"]))
    else:
        o = o.iloc[0:0].copy()
    d = delivery_df.copy()
    if "배송예정일" in d.columns:
        d["연월_키"] = month_key(safe_to_datetime(d["배송예정일"]))
    else:
        d = d.iloc[0:0].copy()
    o_m = o[o.get("연월_키", "") == sel_month].copy()
    d_m = d[d.get("연월_키", "") == sel_month].copy()

    with st.expander("1) 리스크 TOP 주문번호 (AS/교환/반품/취소)", expanded=True):
        if "주문번호" not in set(o_m.columns).union(set(d_m.columns)):
            st.info("주문번호 컬럼이 없어 표시할 수 없습니다.")
        else:
            top_n = st.slider("표시 개수", 5, 50, 15, key="risk_top_n")
            view = build_risk_top(o_m, d_m, top_n)
            if view.empty:
                st.info("해당 월에 리스크 이벤트가 없습니다.")
            else:
                show_table(view, int_cols=["리스크점수", "AS", "교환", "반품", "취소"])

    with st.expander("2) AS/교환 급증 상품코드 (전월 대비)", expanded=True):
        if "상품코드" not in d.columns or "배송유형" not in d.columns:
            st.info("상품코드/배송유형 컬럼이 없어 표시할 수 없습니다.")
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
                view = build_issue_spike_view(d_m, d_prev, top_n=30)
                if view.empty:
                    st.info("전월 대비 급증한 상품코드가 없습니다.")
                else:
                    show_table(view, int_cols=["증가", "총이슈(이번달)", "총이슈(전월)", "AS(이번달)", "교환(이번달)", "AS(전월)", "교환(전월)"])

    om_all = build_order_month_summary(order_df, delivery_df)
    om_m = om_all[om_all.get("연월_키", "") == sel_month].copy() if not om_all.empty else pd.DataFrame()

    with st.expander("3) 취소 TOP 판매지국/판매인 (최종기준 vs 이벤트기준)", expanded=True):
        base = valid_bucket_df(om_m)
        if base.empty:
            st.info("해당 월에 집계할 데이터가 없습니다.")
        else:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**판매지국 TOP**")
                g = rank_cancel(base, "판매지국")
                st.info("판매지국 컬럼이 없습니다.") if g.empty else show_table(g.head(20), percent_cols=["취소율(%)"], int_cols=["전체", "정상", "취소"])
            with c2:
                st.markdown("**판매인 TOP**")
                g = rank_cancel(base, "판매인")
                if g.empty:
                    st.info("판매인 컬럼이 없습니다.")
                else:
                    view = g.copy()
                    if "판매지국" in base.columns:
                        seller_to_branch = base.dropna(subset=["판매인"]).groupby("판매인")["판매지국"].first().fillna("").to_dict()
                        view["판매지국"] = view["판매인"].map(seller_to_branch).fillna("")
                        view = add_seller_branch_label(view, seller_col="판매인", branch_col="판매지국", out_col="판매인 (판매지국)")
                        view = view[["판매인 (판매지국)", "전체", "정상", "취소", "취소율(%)"]]
                    else:
                        view = view[["판매인", "전체", "정상", "취소", "취소율(%)"]]
                    show_table(view.head(20), percent_cols=["취소율(%)"], int_cols=["전체", "정상", "취소"])

            st.markdown("**이벤트 기준(원데이터 관점) 판매인 TOP**")
            event_rank = build_event_seller_summary(order_df, delivery_df, sel_month)
            if event_rank.empty:
                st.info("이벤트 기준 집계에 필요한 데이터가 없습니다.")
            else:
                ev = add_seller_branch_label(event_rank.copy(), seller_col="판매인", branch_col="판매지국", out_col="판매인 (판매지국)")
                ev = ev[["판매인 (판매지국)", "이벤트_전체", "정상완료", "취소", "반품", "AS", "교환", "이벤트_취소율(%)", "이벤트_반품율(%)"]].head(20)
                show_table(ev, percent_cols=["이벤트_취소율(%)", "이벤트_반품율(%)"], int_cols=["이벤트_전체", "정상완료", "취소", "반품", "AS", "교환"])

    with st.expander("4) 반품 TOP 판매지국/판매인 (조회 월 기준)", expanded=True):
        base = valid_bucket_df(om_m)
        if base.empty:
            st.info("해당 월에 집계할 데이터가 없습니다.")
        else:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**판매지국 TOP**")
                g = rank_return(base, "판매지국")
                st.info("판매지국 컬럼이 없습니다.") if g.empty else show_table(g.head(20), percent_cols=["반품율(%)"], int_cols=["전체", "정상", "반품"])
            with c2:
                st.markdown("**판매인 TOP**")
                g = rank_return(base, "판매인")
                if g.empty:
                    st.info("판매인 컬럼이 없습니다.")
                else:
                    view = g.copy()
                    if "판매지국" in base.columns:
                        seller_to_branch = base.dropna(subset=["판매인"]).groupby("판매인")["판매지국"].first().fillna("").to_dict()
                        view["판매지국"] = view["판매인"].map(seller_to_branch).fillna("")
                        view = add_seller_branch_label(view, seller_col="판매인", branch_col="판매지국", out_col="판매인 (판매지국)")
                        view = view[["판매인 (판매지국)", "전체", "정상", "반품", "반품율(%)"]]
                    else:
                        view = view[["판매인", "전체", "정상", "반품", "반품율(%)"]]
                    show_table(view.head(20), percent_cols=["반품율(%)"], int_cols=["전체", "정상", "반품"])

    with st.expander("5) R14(14일내 반품) 악성 패턴 탐지", expanded=True):
        r14 = build_r14_summary(order_df, delivery_df)
        if r14.empty:
            st.info("R14 계산에 필요한 완료/반품 데이터가 없습니다.")
        else:
            r14_m = r14[r14["코호트월"].astype(str).eq(sel_month)].copy()
            if r14_m.empty:
                st.info("선택 월에 정상 완료 코호트가 없습니다.")
            else:
                s = build_r14_seller_summary(r14_m)
                if s.empty:
                    st.info("선택 월에 판매인 매핑 가능한 정상 완료 코호트가 없습니다.")
                else:
                    view = s[["판매인 (판매지국)", "정상완료", "R14", "R14율(%)", "R7", "R7율(%)", "의심점수"]].head(30)
                    show_table(view, percent_cols=["R14율(%)", "R7율(%)"], int_cols=["정상완료", "R14", "R7", "의심점수"])
                    st.caption("기준: 코호트월=정상 완료의 배송예정일 월, R14=반품등록일-정상완료 배송예정일이 0~14일.")

                    sellers = [x for x in s["판매인"].dropna().astype(str).tolist() if x.strip()]
                    if sellers:
                        sel_seller = st.selectbox("추세 확인 판매인", sellers, index=0, key="r14_seller_pick")
                        trend = build_r14_seller_trend(r14, sel_seller)
                        if not trend.empty:
                            show_table(trend.tail(12), percent_cols=["R14율(%)", "R7율(%)"], int_cols=["정상완료", "R14", "R7"])
                            st.line_chart(trend.set_index("코호트월")[["R14율(%)", "R7율(%)"]], use_container_width=True)

    with st.expander("6) 주문번호 결합 확인 (샘플)", expanded=False):
        if om_all is None or om_all.empty:
            st.info("결합된 데이터가 없습니다.")
        else:
            key = st.text_input("주문번호로 검색(선택)", value="", key="dbg_order_no")
            dbg = om_all.copy()
            dbg = dbg[dbg["주문번호"].astype(str).str.contains(key.strip())].copy() if key.strip() else dbg.head(30).copy()
            cols = [c for c in ["연월_키", "주문번호", "최종상태", "정상(상세)", "취소발생", "AS발생", "교환발생", "반품발생", "판매인", "판매지국"] if c in dbg.columns]
            if not cols:
                st.info("표시할 컬럼이 없습니다.")
            else:
                show_table(dbg[cols].copy(), int_cols=["정상(상세)", "취소발생", "AS발생", "교환발생", "반품발생"])
            if order_df is not None and not order_df.empty:
                date_col = "등록일" if "등록일" in order_df.columns else ("배송예정일" if "배송예정일" in order_df.columns else None)
                if date_col:
                    dt = safe_to_datetime(order_df[date_col])
                    if dt.notna().any():
                        st.caption(f"주문 데이터 범위({date_col}): {dt.min().date()} ~ {dt.max().date()} / 이 범위 밖 주문번호는 판매인·판매지국이 비어 보일 수 있음")
