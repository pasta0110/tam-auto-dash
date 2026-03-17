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


def build_exception_pack(delivery_df: pd.DataFrame, ctx: dict):
    if delivery_df is None or delivery_df.empty:
        return {"kpi": {}, "queue": pd.DataFrame(), "causes": pd.DataFrame(), "abnormal": pd.DataFrame()}

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
        "리스크점수",
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
    return {"kpi": kpi, "queue": queue, "causes": causes, "abnormal": abnormal, "excluded_count": excluded_count}
