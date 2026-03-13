# tabs/tab1_5_insights.py
# 1.5 인사이트 (월별 AS/교환/반품/취소율)

import pandas as pd
import streamlit as st


def _safe_to_datetime(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")


def _is_cheongho(df: pd.DataFrame) -> pd.Series:
    if "매출처" not in df.columns:
        return pd.Series(True, index=df.index)
    return df["매출처"].astype(str).eq("청호나이스")

def _center_style(df: pd.DataFrame):
    return (
        df.style.set_properties(**{"text-align": "center"})
        .set_table_styles([{"selector": "th", "props": [("text-align", "center")]}])
    )


def _styled_table(df: pd.DataFrame, percent_cols=(), int_cols=()):
    sty = _center_style(df)
    fmt = {}
    for c in percent_cols:
        if c in df.columns:
            fmt[c] = "{:.2f}"
    for c in int_cols:
        if c in df.columns:
            fmt[c] = "{:,.0f}"
    if fmt:
        sty = sty.format(fmt)
    return sty


def _month_key(d: pd.Series) -> pd.Series:
    return d.dt.strftime("%Y-%m")


def _month_key_from_date_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([None] * len(df), index=df.index, dtype="object")
    dt = _safe_to_datetime(df[col])
    return dt.dt.strftime("%Y-%m")


def _seller_branch_map_from_order(order_df: pd.DataFrame) -> pd.DataFrame:
    if order_df is None or order_df.empty or "주문번호" not in order_df.columns:
        return pd.DataFrame(columns=["주문번호", "판매인", "판매지국"])
    o = order_df.copy()
    o = o[_is_cheongho(o)].copy()
    cols = [c for c in ["주문번호", "판매인", "판매지국"] if c in o.columns]
    if "주문번호" not in cols:
        return pd.DataFrame(columns=["주문번호", "판매인", "판매지국"])
    for c in ["판매인", "판매지국"]:
        if c not in cols:
            o[c] = ""
            cols.append(c)
    return (
        o[cols]
        .dropna(subset=["주문번호"])
        .groupby("주문번호", dropna=False)[["판매인", "판매지국"]]
        .agg(lambda x: x.dropna().astype(str).mode().iloc[0] if len(x.dropna()) else "")
        .reset_index()
    )


def _build_event_seller_summary(order_df: pd.DataFrame, delivery_df: pd.DataFrame, month_key: str) -> pd.DataFrame:
    """
    이벤트 기준(원천 이벤트 관점) 판매인 요약.
    - 모수: 해당 월(배송예정일 기준)에 이벤트가 1건 이상 존재한 고유 주문번호 수
    - 상태별 수치: 같은 주문번호가 여러 상태를 가질 수 있으므로 합은 모수를 초과할 수 있음
    """
    if delivery_df is None or delivery_df.empty or "주문번호" not in delivery_df.columns:
        return pd.DataFrame()

    d = delivery_df.copy()
    d = d[_is_cheongho(d)].copy()
    if "배송예정일" not in d.columns:
        return pd.DataFrame()

    d["연월_키"] = _month_key(_safe_to_datetime(d["배송예정일"]))
    d = d[d["연월_키"].eq(month_key)].copy()
    if d.empty:
        return pd.DataFrame()

    map_df = _seller_branch_map_from_order(order_df)
    d = d.merge(map_df, on="주문번호", how="left")
    seller_col = "판매인"
    branch_col = "판매지국"

    ship_type = d["배송유형"].astype(str) if "배송유형" in d.columns else pd.Series("", index=d.index)
    order_type = d["주문유형"].astype(str) if "주문유형" in d.columns else pd.Series("", index=d.index)
    order_stat = d["주문상태"].astype(str) if "주문상태" in d.columns else pd.Series("", index=d.index)
    ship_stat = d["배송상태"].astype(str) if "배송상태" in d.columns else pd.Series("", index=d.index)

    is_complete = order_stat.str.contains("완료", na=False) | ship_stat.str.contains("완료|4", na=False)
    is_normal_complete = order_type.eq("정상") & is_complete
    is_cancel = ship_stat.eq("미설치") | order_stat.eq("주문취소")
    is_return = ship_type.isin(["반품", "회수"]) | order_type.eq("반품")
    is_as = ship_type.eq("AS")
    is_exchange = ship_type.eq("교환")

    key_cols = ["주문번호", seller_col] + ([branch_col] if branch_col else [])
    dm = d[key_cols].copy()
    dm["정상완료_evt"] = is_normal_complete.astype(int)
    dm["취소_evt"] = is_cancel.astype(int)
    dm["반품_evt"] = is_return.astype(int)
    dm["AS_evt"] = is_as.astype(int)
    dm["교환_evt"] = is_exchange.astype(int)

    by_order = (
        dm.groupby(key_cols, dropna=False)[["정상완료_evt", "취소_evt", "반품_evt", "AS_evt", "교환_evt"]]
        .max()
        .reset_index()
    )
    out = (
        by_order.groupby(seller_col, dropna=False)
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
    out = out.rename(columns={seller_col: "판매인"})
    if branch_col:
        seller_to_branch = (
            by_order.groupby(seller_col)[branch_col]
            .agg(lambda x: x.dropna().astype(str).mode().iloc[0] if len(x.dropna()) else "")
            .to_dict()
        )
        out["판매지국"] = out["판매인"].map(seller_to_branch).fillna("")
    out["이벤트_취소율(%)"] = (out["취소"] / out["이벤트_전체"] * 100).fillna(0).round(2)
    out["이벤트_반품율(%)"] = (out["반품"] / out["이벤트_전체"] * 100).fillna(0).round(2)
    return out.sort_values(["반품", "취소", "이벤트_전체"], ascending=False)


def _build_r14_summary(order_df: pd.DataFrame, delivery_df: pd.DataFrame) -> pd.DataFrame:
    """
    R14(배송예정일 기준 14일 내 반품/회수) 코호트 계산.
    - 코호트 월: 정상 완료 주문의 배송예정일 연월
    - R14 조건: 0 <= (첫 반품 등록일 - 정상 완료 배송예정일) <= 14
    """
    if delivery_df is None or delivery_df.empty or "주문번호" not in delivery_df.columns:
        return pd.DataFrame()

    d = delivery_df.copy()
    d = d[_is_cheongho(d)].copy()
    if d.empty:
        return pd.DataFrame()

    sched_col = "배송예정일" if "배송예정일" in d.columns else None
    reg_col = "등록일" if "등록일" in d.columns else None
    if sched_col is None:
        return pd.DataFrame()

    d["배송예정일_DT"] = _safe_to_datetime(d[sched_col])
    d["등록일_DT"] = _safe_to_datetime(d[reg_col]) if reg_col else pd.NaT

    map_df = _seller_branch_map_from_order(order_df)
    d = d.merge(map_df, on="주문번호", how="left")
    if "주문번호" not in d.columns:
        return pd.DataFrame()

    ship_type = d["배송유형"].astype(str) if "배송유형" in d.columns else pd.Series("", index=d.index)
    order_type = d["주문유형"].astype(str) if "주문유형" in d.columns else pd.Series("", index=d.index)
    order_stat = d["주문상태"].astype(str) if "주문상태" in d.columns else pd.Series("", index=d.index)
    ship_stat = d["배송상태"].astype(str) if "배송상태" in d.columns else pd.Series("", index=d.index)

    is_complete = order_stat.str.contains("완료", na=False) | ship_stat.str.contains("완료|4", na=False)
    normal_complete = order_type.eq("정상") & is_complete & d["배송예정일_DT"].notna()
    is_return = ship_type.isin(["반품", "회수"]) | order_type.eq("반품")

    comp = d[normal_complete].copy()
    if comp.empty:
        return pd.DataFrame()
    comp = comp.sort_values("배송예정일_DT")
    comp_first = (
        comp.groupby("주문번호", dropna=False)
        .agg(
            정상완료일=("배송예정일_DT", "min"),
            판매인=("판매인", lambda x: x.dropna().astype(str).iloc[0] if len(x.dropna()) else ""),
            판매지국=("판매지국", lambda x: x.dropna().astype(str).iloc[0] if len(x.dropna()) else ""),
        )
        .reset_index()
    )
    comp_first["코호트월"] = comp_first["정상완료일"].dt.strftime("%Y-%m")

    ret = d[is_return & d["등록일_DT"].notna()].copy()
    if ret.empty:
        out = comp_first.copy()
        out["반품등록일"] = pd.NaT
        out["반품소요일"] = pd.NA
        out["R14"] = 0
        out["R7"] = 0
        return out

    ret = ret.sort_values("등록일_DT")
    ret_first = ret.groupby("주문번호", dropna=False)["등록일_DT"].min().reset_index(name="반품등록일")

    out = comp_first.merge(ret_first, on="주문번호", how="left")
    out["반품소요일"] = (out["반품등록일"] - out["정상완료일"]).dt.days
    out["R14"] = ((out["반품소요일"] >= 0) & (out["반품소요일"] <= 14)).astype(int)
    out["R7"] = ((out["반품소요일"] >= 0) & (out["반품소요일"] <= 7)).astype(int)
    return out


def _build_order_month_summary(order_df: pd.DataFrame, delivery_df: pd.DataFrame) -> pd.DataFrame:
    """
    주문번호(주문 단위)로 월별(배송예정일 기준) 상태를 1건으로 요약합니다.
    - Key: (연월_키, 주문번호) 1건
    - 정의
      - AS: 배송유형 == 'AS'
      - 교환: 배송유형 == '교환'
      - 반품: 배송유형 in ('반품','회수') or 주문유형 == '반품'
      - 취소: 배송상태 == '미설치'
      - 정상(상세): 주문유형=='정상' AND 주문상태!='주문취소' AND 배송유형=='정상' AND 배송상태!='미설치'
    """
    if delivery_df is None or delivery_df.empty or "주문번호" not in delivery_df.columns:
        return pd.DataFrame()

    d = delivery_df.copy()
    if "매출처" in d.columns:
        d = d[d["매출처"].astype(str).eq("청호나이스")].copy()

    if "배송예정일" not in d.columns:
        return pd.DataFrame()

    d_dt = _safe_to_datetime(d["배송예정일"])
    d = d.assign(연월_키=_month_key(d_dt))
    d = d[d["연월_키"].notna()].copy()
    if d.empty:
        return pd.DataFrame()

    ship_type = d["배송유형"].astype(str) if "배송유형" in d.columns else pd.Series("", index=d.index)
    order_type = d["주문유형"].astype(str) if "주문유형" in d.columns else pd.Series("", index=d.index)
    order_stat = d["주문상태"].astype(str) if "주문상태" in d.columns else pd.Series("", index=d.index)
    ship_stat = d["배송상태"].astype(str) if "배송상태" in d.columns else pd.Series("", index=d.index)

    is_cancel = ship_stat.eq("미설치")
    is_exchange = ship_type.eq("교환")
    is_as = ship_type.eq("AS")
    is_return = ship_type.isin(["반품", "회수"]) | order_type.eq("반품")
    is_normal_strict = (
        order_type.eq("정상")
        & ~order_stat.eq("주문취소")
        & ship_type.eq("정상")
        & ~ship_stat.eq("미설치")
    )

    by_order_month = (
        d.assign(
            _cancel=is_cancel.astype(int),
            _exchange=is_exchange.astype(int),
            _as=is_as.astype(int),
            _return=is_return.astype(int),
            _normal=is_normal_strict.astype(int),
        )
        .groupby(["연월_키", "주문번호"], dropna=False)[["_cancel", "_exchange", "_as", "_return", "_normal"]]
        .max()
        .reset_index()
        .rename(
            columns={
                "_cancel": "취소발생",
                "_exchange": "교환발생",
                "_as": "AS발생",
                "_return": "반품발생",
                "_normal": "정상(상세)",
            }
        )
    )

    def _final(row) -> str:
        if int(row.get("반품발생", 0)) > 0:
            return "반품"
        if int(row.get("교환발생", 0)) > 0:
            return "교환"
        if int(row.get("AS발생", 0)) > 0:
            return "AS"
        if int(row.get("정상(상세)", 0)) > 0:
            return "정상"
        if int(row.get("취소발생", 0)) > 0:
            return "취소"
        return "정상"

    by_order_month["최종상태"] = by_order_month.apply(_final, axis=1)

    # 주문정보 매핑(있으면) - join key는 주문번호만 사용
    o = order_df.copy() if order_df is not None else pd.DataFrame()
    if not o.empty and "주문번호" in o.columns:
        if "매출처" in o.columns:
            o = o[o["매출처"].astype(str).eq("청호나이스")].copy()

        cols = [c for c in ["주문번호", "판매인", "판매지국", "수취인", "상품코드", "상품명", "등록일"] if c in o.columns]
        if cols:
            agg = {}
            for c in cols:
                if c == "주문번호":
                    continue
                if c == "등록일":
                    agg[c] = "min"
                else:
                    agg[c] = lambda x: x.dropna().astype(str).mode().iloc[0] if len(x.dropna()) else ""
            base = o[cols].dropna(subset=["주문번호"]).groupby("주문번호", dropna=False).agg(agg).reset_index()
            by_order_month = by_order_month.merge(base, on="주문번호", how="left")

    return by_order_month


def _kpi_table(delivery_df: pd.DataFrame) -> pd.DataFrame:
    """
    - 날짜 기준: 배송예정일
    - 집계 단위: 주문번호(주문 단위) 1건
    - AS: 배송유형='AS'
    - 교환: 배송유형='교환'
    - 반품: 배송유형 in ('반품','회수') 또는 주문유형='반품'
    - 취소: 배송상태='미설치'
    - 정상(상세): 아래 기준 충족
      1) 주문유형 : 정상
      2) 주문상태 : 주문취소 빼고 다
      3) 배송유형 : 정상
      4) 배송상태 : 미설치 빼고 다

    ✅ 전체는 아래 5개 버킷의 합으로 정의됩니다.
       전체 = 정상 + AS + 교환 + 반품 + 취소
    """
    # delivery -> (월, 주문번호) 1건 요약
    om = _build_order_month_summary(pd.DataFrame(), delivery_df)
    if om.empty:
        return pd.DataFrame()

    # 정상은 '정상(상세)'가 True인 주문만 정상으로 인정하고,
    # 최종상태가 '정상'이지만 상세 정상 조건이 불명확한 건은 미분류로 표기합니다.
    bucket = pd.Series("미분류", index=om.index)
    bucket[om["최종상태"].astype(str).eq("취소")] = "취소"
    bucket[(bucket == "미분류") & om["최종상태"].astype(str).eq("반품")] = "반품"
    bucket[(bucket == "미분류") & om["최종상태"].astype(str).eq("교환")] = "교환"
    bucket[(bucket == "미분류") & om["최종상태"].astype(str).eq("AS")] = "AS"
    bucket[(bucket == "미분류") & om["최종상태"].astype(str).eq("정상") & (om["정상(상세)"] > 0)] = "정상"
    om["버킷"] = bucket

    months = sorted(set(om["연월_키"].dropna().unique()))
    rows = []
    for m in months:
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


def render(order_df: pd.DataFrame, delivery_df: pd.DataFrame, ctx: dict):
    st.subheader("📌 1.5 인사이트")
    # st.dataframe은 숫자/문자 컬럼별 기본 정렬이 강제되는 경우가 있어
    # 가운데 정렬 보장을 위해 이 탭은 st.table(Styler)로 렌더링합니다.
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

    kpi_df = _kpi_table(delivery_df)
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
    c1.metric("AS율(%)", f"{row['AS율']:.2f}", f"{row['AS']}건(주문)")
    c2.metric("교환율(%)", f"{row['교환율']:.2f}", f"{row['교환']}건(주문)")
    c3.metric("반품율(%)", f"{row['반품율']:.2f}", f"{row['반품']}건(주문)")
    c4.metric("취소율(%)", f"{row['취소율']:.2f}", f"{row['취소']}건(주문)")

    st.subheader("월별 비정상 유형별 분석")

    # 표 출력(전체)
    show = kpi_df.copy()
    show = show.set_index("월")
    # 미분류는 검증용(표에는 숨기고 경고로만 사용)
    unclassified_total = int(show["미분류"].sum()) if "미분류" in show.columns else 0
    if "미분류" in show.columns:
        show = show.drop(columns=["미분류"])
    show = show.rename(
        columns={
            "AS율": "AS율(%)",
            "교환율": "교환율(%)",
            "반품율": "반품율(%)",
            "취소율": "취소율(%)",
        }
    )
    st.table(
        _styled_table(
            show,
            percent_cols=["AS율(%)", "교환율(%)", "반품율(%)", "취소율(%)"],
            int_cols=["전체", "정상", "AS", "교환", "반품", "취소"],
        )
    )

    if unclassified_total:
        st.warning(f"⚠️ 미분류 데이터가 {unclassified_total}건 있습니다. (전체 합계에는 포함되지 않음)")

    st.caption("날짜는 배송예정일 기준, 집계 단위는 '주문번호'입니다. '전체'는 5개 버킷(정상/AS/교환/반품/취소)의 합이며 '정상'은 상세 기준을 충족한 주문만 포함합니다.")

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
            # 정의(요청 기준)
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

            c_as = _counts(d_as, "AS")
            c_ex = _counts(d_exchange, "교환")
            c_ret = _counts(d_return, "반품")
            c_can = _counts(d_cancel, "취소")

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
                st.table(_styled_table(view, int_cols=["리스크점수", "AS", "교환", "반품", "취소"]))

    # 2) AS/교환 급증 상품코드
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

                def _issue_counts(df: pd.DataFrame) -> pd.DataFrame:
                    as_df = df[df["배송유형"].astype(str).eq("AS")].copy()
                    ex_df = df[df["배송유형"].astype(str).eq("교환")].copy()

                    as_c = as_df.groupby("상품코드").size().rename("AS").reset_index()
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

                cand = merged[(merged["총이슈_이번달"] > 0) & (merged["증가"] > 0)].copy()
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
                    st.table(
                        _styled_table(
                            view,
                            int_cols=[
                                "증가",
                                "총이슈(이번달)",
                                "총이슈(전월)",
                                "AS(이번달)",
                                "교환(이번달)",
                                "AS(전월)",
                                "교환(전월)",
                            ],
                        )
                    )

    # 공통: 주문번호(주문 단위) 월 요약
    om_all = _build_order_month_summary(order_df, delivery_df)
    om_m = om_all[om_all.get("연월_키", "") == sel_month].copy() if not om_all.empty else pd.DataFrame()

    def _valid_bucket_df(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        out = df.copy()
        out["버킷"] = out["최종상태"].astype(str)
        out.loc[(out["버킷"] == "정상") & ~(out.get("정상(상세)", 0) > 0), "버킷"] = "미분류"
        return out[out["버킷"].isin(["정상", "AS", "교환", "반품", "취소"])].copy()

    # 3) 취소 TOP 판매지국/판매인
    with st.expander("3) 취소 TOP 판매지국/판매인 (최종기준 vs 이벤트기준)", expanded=True):
        base = _valid_bucket_df(om_m)
        if base.empty:
            st.info("해당 월에 집계할 데이터가 없습니다.")
        else:
            def _cancel_rank(col: str) -> pd.DataFrame:
                if col not in base.columns:
                    return pd.DataFrame()
                g = (
                    base.groupby(col, dropna=False)
                    .agg(전체=("주문번호", "size"), 정상=("버킷", lambda x: int((x == "정상").sum())), 취소=("버킷", lambda x: int((x == "취소").sum())))
                    .reset_index()
                )
                g["취소율(%)"] = (g["취소"] / g["전체"] * 100).round(2)
                return g.sort_values(["취소", "취소율(%)"], ascending=False)

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**판매지국 TOP**")
                g = _cancel_rank("판매지국")
                if g.empty:
                    st.info("판매지국 컬럼이 없습니다.")
                else:
                    st.table(_styled_table(g.head(20), percent_cols=["취소율(%)"], int_cols=["전체", "정상", "취소"]))
            with c2:
                st.markdown("**판매인 TOP**")
                g = _cancel_rank("판매인")
                if g.empty:
                    st.info("판매인 컬럼이 없습니다.")
                else:
                    view = g.copy()
                    if "판매지국" in base.columns:
                        seller_to_branch = (
                            base.dropna(subset=["판매인"])
                            .groupby("판매인")["판매지국"]
                            .agg(lambda x: x.dropna().astype(str).mode().iloc[0] if len(x.dropna()) else "")
                            .to_dict()
                        )
                        view["판매지국"] = view["판매인"].map(seller_to_branch).fillna("")
                        view["판매인 (판매지국)"] = view.apply(
                            lambda r: f"{r['판매인']} ({r['판매지국']})" if str(r.get("판매지국", "")).strip() else str(r["판매인"]),
                            axis=1,
                        )
                        view = view[["판매인 (판매지국)", "전체", "정상", "취소", "취소율(%)"]]
                    else:
                        view = view[["판매인", "전체", "정상", "취소", "취소율(%)"]]
                    st.table(_styled_table(view.head(20), percent_cols=["취소율(%)"], int_cols=["전체", "정상", "취소"]))

            st.markdown("**이벤트 기준(원데이터 관점) 판매인 TOP**")
            event_rank = _build_event_seller_summary(order_df, delivery_df, sel_month)
            if event_rank.empty:
                st.info("이벤트 기준 집계에 필요한 데이터가 없습니다.")
            else:
                ev = event_rank.copy()
                ev["판매인 (판매지국)"] = ev.apply(
                    lambda r: f"{r['판매인']} ({r.get('판매지국','')})" if str(r.get("판매지국", "")).strip() else str(r["판매인"]),
                    axis=1,
                )
                ev = ev[
                    [
                        "판매인 (판매지국)",
                        "이벤트_전체",
                        "정상완료",
                        "취소",
                        "반품",
                        "AS",
                        "교환",
                        "이벤트_취소율(%)",
                        "이벤트_반품율(%)",
                    ]
                ].head(20)
                st.table(
                    _styled_table(
                        ev,
                        percent_cols=["이벤트_취소율(%)", "이벤트_반품율(%)"],
                        int_cols=["이벤트_전체", "정상완료", "취소", "반품", "AS", "교환"],
                    )
                )

    # 4) 반품 TOP 판매지국/판매인
    with st.expander("4) 반품 TOP 판매지국/판매인 (조회 월 기준)", expanded=True):
        base = _valid_bucket_df(om_m)
        if base.empty:
            st.info("해당 월에 집계할 데이터가 없습니다.")
        else:
            def _return_rank(col: str) -> pd.DataFrame:
                if col not in base.columns:
                    return pd.DataFrame()
                g = (
                    base.groupby(col, dropna=False)
                    .agg(전체=("주문번호", "size"), 정상=("버킷", lambda x: int((x == "정상").sum())), 반품=("버킷", lambda x: int((x == "반품").sum())))
                    .reset_index()
                )
                g["반품율(%)"] = (g["반품"] / g["전체"] * 100).round(2)
                return g.sort_values(["반품", "반품율(%)"], ascending=False)

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**판매지국 TOP**")
                g = _return_rank("판매지국")
                if g.empty:
                    st.info("판매지국 컬럼이 없습니다.")
                else:
                    st.table(_styled_table(g.head(20), percent_cols=["반품율(%)"], int_cols=["전체", "정상", "반품"]))
            with c2:
                st.markdown("**판매인 TOP**")
                g = _return_rank("판매인")
                if g.empty:
                    st.info("판매인 컬럼이 없습니다.")
                else:
                    view = g.copy()
                    if "판매지국" in base.columns:
                        seller_to_branch = (
                            base.dropna(subset=["판매인"])
                            .groupby("판매인")["판매지국"]
                            .agg(lambda x: x.dropna().astype(str).mode().iloc[0] if len(x.dropna()) else "")
                            .to_dict()
                        )
                        view["판매지국"] = view["판매인"].map(seller_to_branch).fillna("")
                        view["판매인 (판매지국)"] = view.apply(
                            lambda r: f"{r['판매인']} ({r['판매지국']})" if str(r.get("판매지국", "")).strip() else str(r["판매인"]),
                            axis=1,
                        )
                        view = view[["판매인 (판매지국)", "전체", "정상", "반품", "반품율(%)"]]
                    else:
                        view = view[["판매인", "전체", "정상", "반품", "반품율(%)"]]
                    st.table(_styled_table(view.head(20), percent_cols=["반품율(%)"], int_cols=["전체", "정상", "반품"]))

    # 5) R14 악성 패턴 탐지
    with st.expander("5) R14(14일내 반품) 악성 패턴 탐지", expanded=True):
        r14 = _build_r14_summary(order_df, delivery_df)
        if r14.empty:
            st.info("R14 계산에 필요한 완료/반품 데이터가 없습니다.")
        else:
            r14_m = r14[r14["코호트월"].astype(str).eq(sel_month)].copy()
            if r14_m.empty:
                st.info("선택 월에 정상 완료 코호트가 없습니다.")
            else:
                seller_col = "판매인" if "판매인" in r14_m.columns else None
                if seller_col is None:
                    st.info("판매인 정보가 없어 R14 판매인 분석을 표시할 수 없습니다.")
                else:
                    s = (
                        r14_m.groupby(seller_col, dropna=False)
                        .agg(
                            정상완료=("주문번호", "size"),
                            R14=("R14", "sum"),
                            R7=("R7", "sum"),
                        )
                        .reset_index()
                        .rename(columns={seller_col: "판매인"})
                    )
                    s["판매인"] = s["판매인"].astype(str).fillna("").str.strip()
                    s = s[s["판매인"] != ""].copy()
                    if s.empty:
                        st.info("선택 월에 판매인 매핑 가능한 정상 완료 코호트가 없습니다.")
                        return
                    if "판매지국" in r14_m.columns:
                        seller_to_branch = (
                            r14_m.groupby("판매인")["판매지국"]
                            .agg(lambda x: x.dropna().astype(str).mode().iloc[0] if len(x.dropna()) else "")
                            .to_dict()
                        )
                        s["판매지국"] = s["판매인"].map(seller_to_branch).fillna("")
                    s["R14율(%)"] = (s["R14"] / s["정상완료"] * 100).fillna(0).round(2)
                    s["R7율(%)"] = (s["R7"] / s["정상완료"] * 100).fillna(0).round(2)
                    s["의심점수"] = (
                        (s["R14율(%)"] >= 15).astype(int) * 2
                        + (s["R14"] >= 5).astype(int) * 2
                        + (s["R7율(%)"] >= 10).astype(int) * 1
                    )
                    s = s.sort_values(["의심점수", "R14율(%)", "R14", "정상완료"], ascending=False)
                    s["판매인 (판매지국)"] = s.apply(
                        lambda r: f"{r['판매인']} ({r.get('판매지국','')})" if str(r.get("판매지국", "")).strip() else str(r["판매인"]),
                        axis=1,
                    )
                    view = s[
                        [
                            "판매인 (판매지국)",
                            "정상완료",
                            "R14",
                            "R14율(%)",
                            "R7",
                            "R7율(%)",
                            "의심점수",
                        ]
                    ].head(30)
                    st.table(
                        _styled_table(
                            view,
                            percent_cols=["R14율(%)", "R7율(%)"],
                            int_cols=["정상완료", "R14", "R7", "의심점수"],
                        )
                    )
                    st.caption(
                        "기준: 코호트월=정상 완료의 배송예정일 월, R14=반품등록일-정상완료 배송예정일이 0~14일."
                    )

                    # 판매인 월 추세
                    sellers = [x for x in s["판매인"].dropna().astype(str).tolist() if x.strip()]
                    if sellers:
                        sel_seller = st.selectbox("추세 확인 판매인", sellers, index=0, key="r14_seller_pick")
                        t = r14[r14["판매인"].astype(str).eq(sel_seller)].copy()
                        if not t.empty:
                            trend = (
                                t.groupby("코호트월", dropna=False)
                                .agg(정상완료=("주문번호", "size"), R14=("R14", "sum"), R7=("R7", "sum"))
                                .reset_index()
                                .sort_values("코호트월")
                            )
                            trend["R14율(%)"] = (trend["R14"] / trend["정상완료"] * 100).fillna(0).round(2)
                            trend["R7율(%)"] = (trend["R7"] / trend["정상완료"] * 100).fillna(0).round(2)
                            st.table(
                                _styled_table(
                                    trend.tail(12),
                                    percent_cols=["R14율(%)", "R7율(%)"],
                                    int_cols=["정상완료", "R14", "R7"],
                                )
                            )
                            st.line_chart(
                                trend.set_index("코호트월")[["R14율(%)", "R7율(%)"]],
                                use_container_width=True,
                            )

    # 6) 주문번호 결합 확인 (디버그)
    with st.expander("6) 주문번호 결합 확인 (샘플)", expanded=False):
        if om_all is None or om_all.empty:
            st.info("결합된 데이터가 없습니다.")
        else:
            key = st.text_input("주문번호로 검색(선택)", value="", key="dbg_order_no")
            dbg = om_all.copy()
            if key.strip():
                dbg = dbg[dbg["주문번호"].astype(str).str.contains(key.strip())].copy()
            else:
                dbg = dbg.head(30).copy()

            cols = [c for c in ["연월_키", "주문번호", "최종상태", "정상(상세)", "취소발생", "AS발생", "교환발생", "반품발생", "판매인", "판매지국"] if c in dbg.columns]
            if not cols:
                st.info("표시할 컬럼이 없습니다.")
            else:
                view = dbg[cols].copy()
                st.table(_styled_table(view, int_cols=["정상(상세)", "취소발생", "AS발생", "교환발생", "반품발생"]))

            # 주문 데이터 범위 안내 (판매인/지국이 NaN인 이유 확인용)
            if order_df is not None and not order_df.empty:
                date_col = "등록일" if "등록일" in order_df.columns else ("배송예정일" if "배송예정일" in order_df.columns else None)
                if date_col:
                    dt = _safe_to_datetime(order_df[date_col])
                    if dt.notna().any():
                        st.caption(
                            f"주문 데이터 범위({date_col}): {dt.min().date()} ~ {dt.max().date()} / 이 범위 밖 주문번호는 판매인·판매지국이 비어 보일 수 있음"
                        )
