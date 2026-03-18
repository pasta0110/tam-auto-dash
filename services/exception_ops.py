from __future__ import annotations

import re
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
    over = int(row.get("기준초과영업일", row.get("초과영업일", 0)) or 0)
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
    # 1) 해피콜 우선 판정
    happy_flag = str(row.get("해피콜", "") or "").strip().upper()
    reg_dt = pd.to_datetime(row.get("주문등록일", row.get("등록일", None)), errors="coerce")
    happy_dt = pd.to_datetime(
        row.get("해피콜일자", row.get("해피콜일", row.get("해피콜일시", row.get("해피콜등록일", None)))),
        errors="coerce",
    )
    if happy_flag in ("", "N", "NO", "FALSE", "0"):
        return "해피콜 진행"
    if happy_flag == "Y":
        if pd.notna(happy_dt) and pd.notna(reg_dt) and happy_dt >= reg_dt:
            return "조치없음(고객협의 일정)"
        return "해피콜 일자 재확인"

    risk = str(row.get("리스크구분", "") or "")
    state = str(row.get("주문상태", "") or "")
    if str(row.get("지연원인(메세지추정)", "") or "").strip() == "고객협의":
        return "조치없음(고객협의 일정)"
    if "중대지연" in risk:
        if "배송중" in state:
            return "배송사 팀장 콜(30분내 ETA) + 고객 즉시안내 + 재배차 승인요청"
        return "센터장 에스컬레이션(즉시) + 당일 우선출고 + 고객 안내 발송"
    if "지연(기준+2)" in risk:
        if "배송준비" in state:
            return "센터 재배차 요청(2시간내) + 당일 출고확정"
        return "배송사 ETA 재확인(1시간내) + 고객 안내 발송"
    if "지연(기준+1)" in risk:
        if "배송준비" in state:
            return "센터 재배차 요청(2시간내) + 당일 출고확정"
        return "배송사 ETA 재확인(1시간내) + 고객 안내 발송"
    return "사전 안내 발송 + 익일 오전 우선확인"


def _standard_lead_days(series: pd.Series) -> pd.Series:
    s = series.astype(str)
    is_capital = s.str.contains("수도권|수도", regex=True, na=False)
    return is_capital.map(lambda x: 3 if x else 4).astype(int)


def _first_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _norm_text(v) -> str:
    s = str(v or "").strip().lower()
    return " ".join(s.split())


def _norm_phone(v) -> str:
    digits = "".join(ch for ch in str(v or "") if ch.isdigit())
    return digits[-11:] if digits else ""


def _person_key_series(df: pd.DataFrame) -> pd.Series:
    name_col = _first_col(df, ["수취인", "수령인", "성명"])
    addr_col = _first_col(df, ["주소", "address"])
    phone_col = _first_col(df, ["수취인연락처", "연락처", "휴대폰번호", "전화번호"])
    name_s = df[name_col].map(_norm_text) if name_col else pd.Series([""] * len(df), index=df.index)
    addr_s = df[addr_col].map(_norm_text) if addr_col else pd.Series([""] * len(df), index=df.index)
    phone_s = df[phone_col].map(_norm_phone) if phone_col else pd.Series([""] * len(df), index=df.index)
    key = name_s + "|" + addr_s + "|" + phone_s
    return key.where(key != "||", "")


def _message_series(df: pd.DataFrame) -> pd.Series:
    msg_cols = [c for c in ["상담메세지", "상담메시지", "배송메세지", "배송메시지", "배송메모", "비고"] if c in df.columns]
    if not msg_cols:
        return pd.Series([""] * len(df), index=df.index)
    m = df[msg_cols].fillna("").astype(str).agg(" ".join, axis=1)
    return m.map(_norm_text)


def _infer_reason_from_message(message: str) -> str:
    m = str(message or "")
    if not m:
        return "메세지 근거 부족"
    m_norm = re.sub(r"[^0-9a-z가-힣]+", "", m.lower())

    def _hit(keywords: list[str]) -> bool:
        raw = m.lower()
        for kw in keywords:
            k = str(kw).lower()
            if k in raw:
                return True
            k_norm = re.sub(r"[^0-9a-z가-힣]+", "", k)
            if k_norm and k_norm in m_norm:
                return True
        return False

    def _is_contract_term_note(text: str) -> bool:
        t = str(text or "").lower()
        if not t:
            return False
        # 계약/조건 메모로 자주 쓰는 키워드
        contract_kw = [
            "연락후", "계좌완", "핸본인", "본인", "의", "반환", "소모",
            "점검", "개월", "연체", "총", "대", "위", "특별판매", "일시불", "렌탈",
        ]
        kw_hit = sum(1 for kw in contract_kw if kw in t)
        # 숫자/기호 기반 조건 토큰(예: P(72-4), 의72, 위10%, 연체6%)
        token_pat = re.compile(r"(?:[a-z]\(\d{1,3}-\d{1,3}\)|의\d{1,3}|위\d{1,3}%|연체\d{1,3}%|반환\d{1,3}|\d+개월|총\d+대)")
        token_hits = len(token_pat.findall(t))
        slash_density = t.count("/") >= 3
        # 키워드+토큰이 함께 있거나, 슬래시 조합 메모가 많은 경우 계약조건 메모로 간주
        return (kw_hit >= 2 and token_hits >= 1) or (token_hits >= 2) or (kw_hit >= 3 and slash_density)

    # ★ 처리이력 표기(방문/교환/반품/전산매변 등)는 일정 사유가 아닌 이력 메모로 간주
    has_star_marker = any(x in m for x in ["★", "☆", "※"])
    if has_star_marker and _hit(["방문", "교환", "반품", "전산매변", "매변", "매출상태변경", "상태변경"]):
        return "일정무관(처리이력)"
    if _is_contract_term_note(m):
        return "일정무관(계약조건)"

    rules = [
        ("일정무관(계약조건)", ["연락후", "계좌완", "핸본인", "반환", "점검", "연체", "총", "개월"]),
        ("일정무관(처리이력)", ["전산매변", "매출상태변경", "상태변경"]),
        ("일정무관(전자서명)", ["전자동의", "전자 동의", "전자서명동의", "전자 서명 동의"]),
        ("일정무관(판매조건)", ["특별판매", "일시불", "렌탈", "약정", "할부"]),
        ("고객의사 대기", ["컨택하지말", "연락하지말", "고민해본", "고민해본다", "고민해본다고", "보류요청", "보류 요청", "보류", "대기요청"]),
        ("고객협의", ["이사", "입주", "고객요청", "고객 사정", "고객사정", "부재", "시간", "오후", "주말", "재방문", "일정", "조율", "협의", "동의"]),
        ("취소/반품 연관", ["취소", "반품", "철회"]),
        ("판매/상담 이슈", ["판매인", "판매자", "상담", "안내", "설명"]),
        ("주소/연락처 정보 오류", ["주소오류", "주소 불명", "연락처오류", "오기입", "오입력", "번호 오류"]),
        ("재고/출고 지연", ["재고", "입고", "품절", "출고지연", "물류", "창고"]),
        ("설치/배차 지연", ["기사", "설치", "배차", "방문", "스케줄"]),
    ]
    for label, kws in rules:
        if _hit(kws):
            return label
    return "기타 운영 이슈"


def _final_cause_tag(row: pd.Series) -> str:
    # 우선순위: 상담메세지 기반 추정 > 상태 기반 추정
    msg_reason = str(row.get("지연원인(메세지추정)", "") or "").strip()
    if msg_reason in ("일정무관(전자서명)", "일정무관(판매조건)", "일정무관(처리이력)", "일정무관(계약조건)"):
        return _cause_tag(row)
    if msg_reason and msg_reason != "메세지 근거 부족":
        if msg_reason == "고객협의":
            return "고객협의"
        return msg_reason
    return _cause_tag(row)


def _build_person_reason_pack(df: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    if df.empty:
        return pd.Series(dtype=object), pd.DataFrame(columns=["동일인키", "동일인주문수", "지연원인(메세지추정)", "상담메세지요약"])
    key_s = _person_key_series(df)
    msg_s = _message_series(df)
    tmp = pd.DataFrame({"동일인키": key_s, "_msg": msg_s}, index=df.index)
    tmp = tmp[tmp["동일인키"] != ""].copy()
    if tmp.empty:
        return key_s, pd.DataFrame(columns=["동일인키", "동일인주문수", "지연원인(메세지추정)", "상담메세지요약"])

    def _merge_msgs(s: pd.Series) -> str:
        vals = [x for x in s.astype(str).tolist() if str(x).strip()]
        uniq = list(dict.fromkeys(vals))
        merged = " | ".join(uniq)
        return merged[:280]

    person = (
        tmp.groupby("동일인키", dropna=False)
        .agg(동일인주문수=("동일인키", "size"), 상담메세지요약=("_msg", _merge_msgs))
        .reset_index()
    )
    person["지연원인(메세지추정)"] = person["상담메세지요약"].map(_infer_reason_from_message)
    return key_s, person


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
            "person_reasons": pd.DataFrame(),
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
    if "배송사_정제" in q.columns:
        q["정상납기기준(영업일)"] = _standard_lead_days(q["배송사_정제"])
    else:
        q["정상납기기준(영업일)"] = 4
    q["초과영업일"] = q["경과영업일(등록→기준일)"] - q["계획리드타임(영업일)"]
    q["기준초과영업일"] = q["경과영업일(등록→기준일)"] - q["정상납기기준(영업일)"]

    q["리스크구분"] = "지연(기준+1)"
    q.loc[q["기준초과영업일"] >= 2, "리스크구분"] = "지연(기준+2)"
    q.loc[q["기준초과영업일"] >= 3, "리스크구분"] = "중대지연(기준+3)"
    q["리스크점수"] = 40
    q.loc[q["기준초과영업일"] >= 1, "리스크점수"] = 80
    q.loc[q["기준초과영업일"] >= 3, "리스크점수"] = 100
    q["원인태그"] = q.apply(_cause_tag, axis=1)
    q["권장조치"] = q.apply(_recommended_action, axis=1)
    person_key_s, person_df = _build_person_reason_pack(df)
    q["동일인키"] = person_key_s.loc[q.index]
    if not person_df.empty:
        q = q.merge(
            person_df[["동일인키", "동일인주문수", "지연원인(메세지추정)", "상담메세지요약"]],
            on="동일인키",
            how="left",
        )
    if "지연원인(메세지추정)" in q.columns:
        q["원인태그"] = q.apply(_final_cause_tag, axis=1)

    q_focus = q.loc[q["기준초과영업일"] >= 1].copy()

    d1 = int((q_focus["기준초과영업일"] == 1).sum()) if "기준초과영업일" in q_focus.columns else 0
    d2 = int((q_focus["기준초과영업일"] == 2).sum()) if "기준초과영업일" in q_focus.columns else 0
    d3p = int((q_focus["기준초과영업일"] >= 3).sum()) if "기준초과영업일" in q_focus.columns else 0
    kpi["delay_d1"] = d1
    kpi["delay_d2"] = d2
    kpi["delay_d3p"] = d3p
    kpi["queue_total"] = int(len(q_focus))
    kpi["within_standard_pending"] = int(len(q) - len(q_focus))

    # 표시 컬럼
    cols = []
    for c in [
        "주문번호",
        reg_col if reg_col else "등록일",
        "배송예정일_DT",
        "정상납기기준(영업일)",
        "계획리드타임(영업일)",
        "경과영업일(등록→기준일)",
        "기준초과영업일",
        "초과영업일",
        "리스크구분",
        "원인태그",
        "리스크점수",
        "권장조치",
        "동일인주문수",
        "지연원인(메세지추정)",
        "상담메세지요약",
        "지연일수",
        "주문상태",
        "배송상태",
        "배송사_정제",
        "수취인",
        "상품명",
        "판매인",
        "담당자",
        "해피콜",
        "해피콜일자",
        "해피콜일",
        "해피콜일시",
        "해피콜등록일",
    ]:
        if c in q_focus.columns:
            cols.append(c)
    queue = q_focus[cols].copy() if cols else q_focus.copy()
    if reg_col and reg_col in queue.columns:
        queue[reg_col] = pd.to_datetime(queue[reg_col], errors="coerce").dt.strftime("%Y-%m-%d")
        queue = queue.rename(columns={reg_col: "주문등록일"})
    if "배송예정일_DT" in queue.columns:
        queue["배송예정일_DT"] = pd.to_datetime(queue["배송예정일_DT"]).dt.strftime("%Y-%m-%d")
        queue = queue.rename(columns={"배송예정일_DT": "배송예정일"})
    queue = queue.sort_values(["리스크점수", "기준초과영업일", "지연일수"], ascending=[False, False, False]).head(300)
    queue = queue.rename(
        columns={
            "정상납기기준(영업일)": "정상납기",
            "계획리드타임(영업일)": "소요일",
            "경과영업일(등록→기준일)": "경과일",
            "기준초과영업일": "납기초과",
            "초과영업일": "소요일초과",
        }
    )

    # 원인 분포(권역 중심)
    if "배송사_정제" in q_focus.columns and not q_focus.empty:
        causes = (
            q_focus.groupby("배송사_정제", dropna=False)
            .agg(예외건수=("주문번호", "size") if "주문번호" in q_focus.columns else ("리스크점수", "size"), 평균지연일=("지연일수", "mean"))
            .reset_index()
            .rename(columns={"배송사_정제": "센터"})
            .sort_values(["예외건수", "평균지연일"], ascending=[False, False])
        )
        causes["평균지연일"] = causes["평균지연일"].round(2)
    else:
        causes = pd.DataFrame(columns=["센터", "예외건수", "평균지연일"])

    if not q_focus.empty and "원인태그" in q_focus.columns:
        cause_tags = (
            q_focus.groupby("원인태그", dropna=False)
            .agg(건수=("주문번호", "size") if "주문번호" in q_focus.columns else ("리스크점수", "size"))
            .reset_index()
            .sort_values("건수", ascending=False)
        )
    else:
        cause_tags = pd.DataFrame(columns=["원인태그", "건수"])

    if not q_focus.empty and "권장조치" in q_focus.columns:
        actions = (
            q_focus.groupby("권장조치", dropna=False)
            .agg(대상건수=("주문번호", "size") if "주문번호" in q_focus.columns else ("리스크점수", "size"))
            .reset_index()
            .sort_values("대상건수", ascending=False)
        )
    else:
        actions = pd.DataFrame(columns=["권장조치", "대상건수"])

    if not q_focus.empty and "동일인키" in q_focus.columns and not person_df.empty:
        person_reasons = (
            q_focus[["동일인키"]]
            .merge(person_df, on="동일인키", how="left")
            .dropna(subset=["동일인키"])
            .drop_duplicates(subset=["동일인키"])
            .sort_values(["동일인주문수"], ascending=[False])
        )
    else:
        person_reasons = pd.DataFrame(columns=["동일인키", "동일인주문수", "지연원인(메세지추정)", "상담메세지요약"])
    center_sla = _build_center_sla(q_focus, scope_df, done, due <= today)
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
        "person_reasons": person_reasons,
        "abnormal": abnormal,
        "excluded_count": excluded_count,
    }
