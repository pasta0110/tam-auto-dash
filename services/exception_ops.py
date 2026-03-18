from __future__ import annotations

import pandas as pd
import config
from utils.date_utils import get_w_days


def _status_col(df: pd.DataFrame) -> str:
    if "배송상태" in df.columns:
        return "배송상태"
    if "delivery_stat_nm" in df.columns:
        return "delivery_stat_nm"
    return "배송상태"


def _contains(s: pd.Series, pat: str) -> pd.Series:
    return s.astype(str).str.contains(pat, na=False)


def _is_complete(df: pd.DataFrame) -> pd.Series:
    col = _status_col(df)
    return _contains(df[col], "완료|4")


def _is_normal(df: pd.DataFrame) -> pd.Series:
    if "주문유형" in df.columns:
        return _contains(df["주문유형"], "정상")
    return pd.Series([True] * len(df), index=df.index)


def _month_key(series_dt: pd.Series) -> pd.Series:
    return pd.to_datetime(series_dt, errors="coerce").dt.strftime("%Y-%m")


def _active_order_state(df: pd.DataFrame) -> pd.Series:
    if "주문상태" not in df.columns:
        return pd.Series([True] * len(df), index=df.index)
    return _contains(df["주문상태"], "주문확정|배송준비|배송중")


def _not_misinstall(df: pd.DataFrame) -> pd.Series:
    col = _status_col(df)
    return ~_contains(df[col], "미설치")


def _workday_delta(start_dt, end_dt) -> int:
    try:
        s = pd.to_datetime(start_dt, errors="coerce")
        e = pd.to_datetime(end_dt, errors="coerce")
        if pd.isna(s) or pd.isna(e):
            return 0
        if e < s:
            return 0
        return int(get_w_days(s.date(), e.date()))
    except Exception:
        return 0


def _cause_tag(row: pd.Series) -> str:
    over = int(row.get("초과영업일", 0) or 0)
    state = str(row.get("주문상태", "") or "")
    if over >= 3:
        if "배송중" in state:
            return "배송중 장기지연"
        if "배송준비" in state:
            return "센터출고 병목"
        return "출고미착수 장기지연"
    if over >= 1:
        if "배송중" in state:
            return "배송중 지연"
        return "약속일 초과"
    if over >= 0:
        return "당일 마감위험"
    return "D+1 임박위험"


def _recommended_action(row: pd.Series) -> str:
    risk = str(row.get("리스크구분", "") or "")
    state = str(row.get("주문상태", "") or "")
    if "중대지연" in risk:
        if "배송중" in state:
            return "배송사 팀장 콜(30분내 ETA) + 고객 즉시안내 + 재배차 승인요청"
        return "센터장 에스컬레이션(즉시) + 당일 우선출고 + 고객 안내 발송"
    if "지연(영업일+1)" in risk:
        if "배송준비" in state:
            return "센터 재배차 요청(2시간내) + 당일 출고확정"
        return "배송사 ETA 재확인(1시간내) + 고객 안내 발송"
    if "당일 미완료" in risk:
        return "당일 컷오프 점검(즉시) + 선피킹/선배차"
    return "사전 안내 발송 + 익일 오전 우선확인"


def _build_center_sla(q: pd.DataFrame, scope_df: pd.DataFrame, done_mask: pd.Series, due_mask: pd.Series) -> pd.DataFrame:
    if "배송사_정제" not in scope_df.columns:
        return pd.DataFrame(columns=["센터", "약속건", "완료건", "SLA(%)", "예외건수"])
    m = scope_df.loc[due_mask].copy()
    if m.empty:
        return pd.DataFrame(columns=["센터", "약속건", "완료건", "SLA(%)", "예외건수"])
    m["_done"] = done_mask.loc[m.index].astype(int)
    center = (
        m.groupby("배송사_정제", dropna=False)
        .agg(약속건=("배송사_정제", "size"), 완료건=("_done", "sum"))
        .reset_index()
        .rename(columns={"배송사_정제": "센터"})
    )
    center["SLA(%)"] = (center["완료건"] / center["약속건"] * 100.0).round(2)
    if not q.empty and "배송사_정제" in q.columns:
        q_counts = (
            q.groupby("배송사_정제", dropna=False)
            .agg(예외건수=("주문번호", "size") if "주문번호" in q.columns else ("리스크점수", "size"))
            .reset_index()
            .rename(columns={"배송사_정제": "센터"})
        )
        center = center.merge(q_counts, on="센터", how="left")
    center["예외건수"] = center["예외건수"].fillna(0).astype(int)
    return center.sort_values(["SLA(%)", "예외건수"], ascending=[True, False])


def _build_capacity_warning(scope_df: pd.DataFrame, today: pd.Timestamp) -> pd.DataFrame:
    if scope_df.empty or "배송예정일_DT" not in scope_df.columns or "배송사_정제" not in scope_df.columns:
        return pd.DataFrame(columns=["센터", "내일예정", "기준치", "초과", "위험도"])
    d = scope_df.copy()
    d["_due"] = pd.to_datetime(d["배송예정일_DT"], errors="coerce").dt.normalize()
    d = d.dropna(subset=["_due"])
    if d.empty:
        return pd.DataFrame(columns=["센터", "내일예정", "기준치", "초과", "위험도"])
    tomorrow = today + pd.Timedelta(days=1)
    tomorrow_cnt = (
        d.loc[d["_due"] == tomorrow]
        .groupby("배송사_정제", dropna=False)
        .size()
        .rename("내일예정")
        .reset_index()
        .rename(columns={"배송사_정제": "센터"})
    )
    hist = d.loc[(d["_due"] >= (today - pd.Timedelta(days=35))) & (d["_due"] <= today)].copy()
    if hist.empty or tomorrow_cnt.empty:
        return pd.DataFrame(columns=["센터", "내일예정", "기준치", "초과", "위험도"])
    base = (
        hist.groupby(["배송사_정제", "_due"], dropna=False)
        .size()
        .rename("일건수")
        .reset_index()
        .groupby("배송사_정제", dropna=False)["일건수"]
        .quantile(0.9)
        .reset_index()
        .rename(columns={"배송사_정제": "센터", "일건수": "기준치"})
    )
    w = tomorrow_cnt.merge(base, on="센터", how="left")
    w["기준치"] = w["기준치"].fillna(0).round().astype(int)
    w["초과"] = w["내일예정"] - w["기준치"]
    w = w[w["초과"] > 0].copy()
    if w.empty:
        return pd.DataFrame(columns=["센터", "내일예정", "기준치", "초과", "위험도"])
    w["위험도"] = "중"
    w.loc[w["초과"] >= 30, "위험도"] = "상"
    w.loc[w["초과"] >= 60, "위험도"] = "최상"
    return w.sort_values(["초과", "내일예정"], ascending=[False, False]).reset_index(drop=True)


def build_exception_pack(delivery_df: pd.DataFrame, ctx: dict):
    if delivery_df is None or delivery_df.empty:
        return {
            "kpi": {},
            "queue": pd.DataFrame(),
            "causes": pd.DataFrame(),
            "center_sla": pd.DataFrame(),
            "capacity_warning": pd.DataFrame(),
            "cause_tags": pd.DataFrame(),
            "actions": pd.DataFrame(),
            "abnormal": pd.DataFrame(),
        }

    df = delivery_df.copy()
    if "배송예정일_DT" not in df.columns and "배송예정일" in df.columns:
        df["배송예정일_DT"] = pd.to_datetime(df["배송예정일"], errors="coerce")
    df = df.dropna(subset=["배송예정일_DT"]).copy()

    normal = _is_normal(df)
    done = _is_complete(df)
    active = _active_order_state(df)
    not_mis = _not_misinstall(df)
    if "주문번호" in df.columns:
        ex_set = {str(x).strip() for x in getattr(config, "EXCEPTION_COMPLETED_ORDER_NOS", set())}
        not_exception = ~df["주문번호"].astype(str).str.strip().isin(ex_set)
    else:
        not_exception = pd.Series([True] * len(df), index=df.index)
    today = pd.to_datetime(ctx.get("yesterday")).normalize() if ctx.get("yesterday") is not None else pd.Timestamp.today().normalize()
    due = pd.to_datetime(df["배송예정일_DT"], errors="coerce").dt.normalize()

    if "주문등록일" in df.columns:
        reg_col = "주문등록일"
    elif "등록일" in df.columns:
        reg_col = "등록일"
    else:
        reg_col = None
    reg_dt = pd.to_datetime(df[reg_col], errors="coerce").dt.normalize() if reg_col else pd.to_datetime(df["배송예정일_DT"], errors="coerce").dt.normalize()

    # SLA proxy KPI (활성 주문 기준, 배송예정일까지 상태 완료 여부)
    scope = normal & active & not_mis & not_exception
    scope_df = df.loc[scope].copy()
    due_until_today = scope & (due <= today)
    ontime_done = due_until_today & done
    overdue = scope & (due < today) & (~done)
    due_today = scope & (due == today) & (~done)
    due_tomorrow = scope & (due == (today + pd.Timedelta(days=1))) & (~done)

    denom = int(due_until_today.sum())
    ontime = int(ontime_done.sum())
    overdue_n = int(overdue.sum())
    due_today_n = int(due_today.sum())
    due_tomorrow_n = int(due_tomorrow.sum())
    ontime_rate = round((ontime / denom * 100.0), 2) if denom > 0 else 0.0

    kpi = {
        "due_until_today": denom,
        "ontime_done": ontime,
        "ontime_rate": ontime_rate,
        "overdue": overdue_n,
        "due_today": due_today_n,
        "due_tomorrow": due_tomorrow_n,
        "at_risk_48h": due_today_n + due_tomorrow_n,
    }

    # Exception queue (행동 우선순위): 활성 주문상태 + 미설치 제외 + 미완료
    q = df.loc[scope & (~done)].copy()
    q_due = pd.to_datetime(q["배송예정일_DT"], errors="coerce").dt.normalize()
    q_reg = pd.to_datetime(q[reg_col], errors="coerce").dt.normalize() if reg_col and reg_col in q.columns else q_due
    q["지연일수"] = (today - q_due).dt.days
    q["계획리드타임(영업일)"] = [
        _workday_delta(s, e) for s, e in zip(q_reg, q_due)
    ]
    q["경과영업일(등록→기준일)"] = [
        _workday_delta(s, today) for s in q_reg
    ]
    q["초과영업일"] = q["경과영업일(등록→기준일)"] - q["계획리드타임(영업일)"]

    q["리스크구분"] = "D+1 임박"
    q.loc[q["초과영업일"] >= 0, "리스크구분"] = "당일 미완료"
    q.loc[q["초과영업일"] >= 1, "리스크구분"] = "지연(영업일+1)"
    q.loc[q["초과영업일"] >= 3, "리스크구분"] = "중대지연(영업일+3)"
    q["리스크점수"] = 40
    q.loc[q["초과영업일"] >= 0, "리스크점수"] = 60
    q.loc[q["초과영업일"] >= 1, "리스크점수"] = 80
    q.loc[q["초과영업일"] >= 3, "리스크점수"] = 100
    q["원인태그"] = q.apply(_cause_tag, axis=1)
    q["권장조치"] = q.apply(_recommended_action, axis=1)

    d1 = int((q["초과영업일"] == 1).sum()) if "초과영업일" in q.columns else 0
    d2 = int((q["초과영업일"] == 2).sum()) if "초과영업일" in q.columns else 0
    d3p = int((q["초과영업일"] >= 3).sum()) if "초과영업일" in q.columns else 0
    kpi["delay_d1"] = d1
    kpi["delay_d2"] = d2
    kpi["delay_d3p"] = d3p
    kpi["queue_total"] = int(len(q))

    # 표시 컬럼
    cols = []
    for c in [
        "주문번호",
        reg_col if reg_col else "등록일",
        "배송예정일_DT",
        "계획리드타임(영업일)",
        "경과영업일(등록→기준일)",
        "초과영업일",
        "리스크구분",
        "원인태그",
        "리스크점수",
        "권장조치",
        "지연일수",
        "주문상태",
        "배송상태",
        "배송사_정제",
        "수취인",
        "상품명",
        "판매인",
        "담당자",
    ]:
        if c in q.columns:
            cols.append(c)
    queue = q[cols].copy() if cols else q.copy()
    if reg_col and reg_col in queue.columns:
        queue[reg_col] = pd.to_datetime(queue[reg_col], errors="coerce").dt.strftime("%Y-%m-%d")
        queue = queue.rename(columns={reg_col: "주문등록일"})
    if "배송예정일_DT" in queue.columns:
        queue["배송예정일_DT"] = pd.to_datetime(queue["배송예정일_DT"]).dt.strftime("%Y-%m-%d")
        queue = queue.rename(columns={"배송예정일_DT": "배송예정일"})
    queue = queue.sort_values(["리스크점수", "초과영업일", "지연일수"], ascending=[False, False, False]).head(300)

    # 원인 분포(권역 중심)
    if "배송사_정제" in q.columns and not q.empty:
        causes = (
            q.groupby("배송사_정제", dropna=False)
            .agg(예외건수=("주문번호", "size") if "주문번호" in q.columns else ("리스크점수", "size"), 평균지연일=("지연일수", "mean"))
            .reset_index()
            .rename(columns={"배송사_정제": "센터"})
            .sort_values(["예외건수", "평균지연일"], ascending=[False, False])
        )
        causes["평균지연일"] = causes["평균지연일"].round(2)
    else:
        causes = pd.DataFrame(columns=["센터", "예외건수", "평균지연일"])

    if not q.empty and "원인태그" in q.columns:
        cause_tags = (
            q.groupby("원인태그", dropna=False)
            .agg(건수=("주문번호", "size") if "주문번호" in q.columns else ("리스크점수", "size"))
            .reset_index()
            .sort_values("건수", ascending=False)
        )
    else:
        cause_tags = pd.DataFrame(columns=["원인태그", "건수"])

    if not q.empty and "권장조치" in q.columns:
        actions = (
            q.groupby("권장조치", dropna=False)
            .agg(대상건수=("주문번호", "size") if "주문번호" in q.columns else ("리스크점수", "size"))
            .reset_index()
            .sort_values("대상건수", ascending=False)
        )
    else:
        actions = pd.DataFrame(columns=["권장조치", "대상건수"])
    center_sla = _build_center_sla(q, scope_df, done, due <= today)
    capacity_warning = _build_capacity_warning(scope_df, today)

    # 월 비정상 이벤트(참고): 취소/반품/교환/AS
    if "배송예정일_DT" in df.columns:
        df["_mkey"] = _month_key(df["배송예정일_DT"])
        this_m = str(ctx.get("m_key") or "")
        abnormal_scope = df[df["_mkey"] == this_m].copy()
    else:
        abnormal_scope = df.copy()

    def _count_order_type(pattern: str) -> int:
        if "주문유형" not in abnormal_scope.columns or abnormal_scope.empty:
            return 0
        return int(_contains(abnormal_scope["주문유형"], pattern).sum())

    abnormal = pd.DataFrame(
        [
            {"유형": "취소", "건수": _count_order_type("취소")},
            {"유형": "반품", "건수": _count_order_type("반품")},
            {"유형": "교환", "건수": _count_order_type("교환")},
            {"유형": "AS", "건수": _count_order_type("^AS$|AS")},
        ]
    )

    excluded_count = int((~not_exception).sum())
    return {
        "kpi": kpi,
        "queue": queue,
        "causes": causes,
        "center_sla": center_sla,
        "capacity_warning": capacity_warning,
        "cause_tags": cause_tags,
        "actions": actions,
        "abnormal": abnormal,
        "excluded_count": excluded_count,
    }
