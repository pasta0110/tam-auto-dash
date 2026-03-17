from __future__ import annotations

import datetime
from datetime import timedelta

import pandas as pd

from utils.date_utils import get_w_days


def build_tab3_prediction(ana_df: pd.DataFrame, ctx: dict, centers: list[str]) -> tuple[list[dict], dict]:
    yesterday = ctx["yesterday"]
    m_key = ctx["m_key"]
    m_start = ctx["m_start"]
    m_end = ctx["m_end"]

    total_w = get_w_days(m_start, m_end)
    passed_w = get_w_days(m_start, yesterday)
    remain_w = total_w - passed_w

    last_30_days_start = yesterday - timedelta(days=30)
    recent_30d_data = ana_df[
        (ana_df["배송예정일_DT"] >= pd.to_datetime(last_30_days_start))
        & (ana_df["배송예정일_DT"] <= pd.to_datetime(yesterday))
    ]
    recent_working_days = get_w_days(last_30_days_start, yesterday)

    sum_curr, sum_avg, sum_remain, sum_total = 0, 0.0, 0, 0
    pred_rows = []
    center_set = set(ana_df["배송사_정제"].unique())

    for v in centers:
        if v not in center_set:
            continue
        curr_act = len(ana_df[(ana_df["배송사_정제"] == v) & (ana_df["연월_키"] == m_key)])
        v_recent_count = len(recent_30d_data[recent_30d_data["배송사_정제"] == v])

        avg_30d = v_recent_count / recent_working_days if recent_working_days > 0 else 0
        rem_pred = int(avg_30d * remain_w)
        projected = curr_act + rem_pred

        sum_curr += curr_act
        sum_avg += avg_30d
        sum_remain += rem_pred
        sum_total += projected

        pred_rows.append(
            {
                "배송사": v,
                "현재 실적(당월)": f"{curr_act} 건",
                "최근 30일 평균": f"{avg_30d:.1f} 건/일",
                f"남은 영업일 예상({remain_w}일)": f"{rem_pred} 건",
                "당월 최종 예측": f"{projected} 건",
            }
        )

    pred_rows.append(
        {
            "배송사": "📌 합계",
            "현재 실적(당월)": f"{sum_curr} 건",
            "최근 30일 평균": f"{sum_avg:.1f} 건/일",
            f"남은 영업일 예상({remain_w}일)": f"{sum_remain} 건",
            "당월 최종 예측": f"{sum_total} 건",
        }
    )

    meta = {"recent_working_days": recent_working_days, "remain_w": remain_w}
    return pred_rows, meta


def _month_start_end(month_key: str):
    y, m = map(int, month_key.split("-"))
    start = datetime.date(y, m, 1)
    if m == 12:
        end = datetime.date(y, 12, 31)
    else:
        end = datetime.date(y, m + 1, 1) - timedelta(days=1)
    return start, end


def find_working_day_date(start: datetime.date, end: datetime.date, day_num: int):
    month_days = pd.date_range(start, end)
    w_count = 0
    for d in month_days:
        if get_w_days(d.date(), d.date()) > 0:
            w_count += 1
            if w_count == day_num:
                return d.date()
    return None


def simulate_month_prediction(
    ana_df: pd.DataFrame, sel_month_key: str, sel_day_num: int, centers: list[str]
) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    sim_m_start, sim_m_end = _month_start_end(sel_month_key)
    s_total_w = get_w_days(sim_m_start, sim_m_end)
    s_real_final = ana_df[ana_df["연월_키"] == sel_month_key]
    sum_actual = len(s_real_final)

    target_date = find_working_day_date(sim_m_start, sim_m_end, sel_day_num)
    if not target_date:
        return pd.DataFrame(), {}, pd.DataFrame()

    s_act_data = ana_df[(ana_df["배송예정일_DT"].dt.date >= sim_m_start) & (ana_df["배송예정일_DT"].dt.date <= target_date)]
    s_30_start = target_date - timedelta(days=30)
    s_recent_30d = ana_df[(ana_df["배송예정일_DT"].dt.date >= s_30_start) & (ana_df["배송예정일_DT"].dt.date <= target_date)]

    s_recent_w = get_w_days(s_30_start, target_date)
    s_remain_w = s_total_w - sel_day_num
    center_set = set(ana_df["배송사_정제"].unique())

    test_rows = []
    sum_curr, sum_final_pred = 0, 0

    for v in centers:
        if v not in center_set:
            continue
        v_curr = len(s_act_data[s_act_data["배송사_정제"] == v])
        v_recent = len(s_recent_30d[s_recent_30d["배송사_정제"] == v])
        v_pace = v_recent / s_recent_w if s_recent_w > 0 else 0
        v_rem_pred = int(v_pace * s_remain_w)
        v_final_pred = v_curr + v_rem_pred
        v_actual = len(s_real_final[s_real_final["배송사_정제"] == v])
        v_acc = (1 - abs((v_actual - v_final_pred) / v_actual)) * 100 if v_actual > 0 else 0
        sum_curr += v_curr
        sum_final_pred += v_final_pred

        test_rows.append(
            {
                "지역센터": v,
                "당시 실적": f"{v_curr}건",
                "일평균 페이스": f"{v_pace:.1f}건/일",
                "예측 최종": f"{v_final_pred}건",
                "실제 결과": f"{v_actual}건",
                "정확도": f"{v_acc:.1f}%",
            }
        )

    total_acc = (1 - abs((sum_actual - sum_final_pred) / sum_actual)) * 100 if sum_actual > 0 else 0
    test_rows.append(
        {
            "지역센터": "📌 합계",
            "당시 실적": f"{sum_curr}건",
            "일평균 페이스": "-",
            "예측 최종": f"{sum_final_pred}건",
            "실제 결과": f"{sum_actual}건",
            "정확도": f"{total_acc:.1f}%",
        }
    )

    acc_hist = []
    temp_w_count = 0
    for d in pd.date_range(sim_m_start, sim_m_end):
        if get_w_days(d.date(), d.date()) == 0:
            continue
        temp_w_count += 1
        if temp_w_count > 24:
            break
        d_date = d.date()
        d_act = len(ana_df[(ana_df["연월_키"] == sel_month_key) & (ana_df["배송예정일_DT"].dt.date <= d_date)])
        d_30_s = d_date - timedelta(days=30)
        d_30_data = ana_df[(ana_df["배송예정일_DT"].dt.date >= d_30_s) & (ana_df["배송예정일_DT"].dt.date <= d_date)]
        d_30_w = get_w_days(d_30_s, d_date)
        d_pace = len(d_30_data) / d_30_w if d_30_w > 0 else 0
        d_pred = d_act + int(d_pace * (s_total_w - temp_w_count))
        d_acc = (1 - abs((sum_actual - d_pred) / sum_actual)) * 100 if sum_actual > 0 else 0
        acc_hist.append({"영업일": f"{temp_w_count}일차", "날짜": d_date.strftime("%m/%d"), "정확도": d_acc})

    meta = {
        "target_date": target_date,
        "sum_actual": sum_actual,
        "total_w": s_total_w,
    }
    return pd.DataFrame(test_rows), meta, pd.DataFrame(acc_hist)


def build_historical_day_trend(
    ana_df: pd.DataFrame, sel_day_num: int, month_from: str = "2025-05", month_to_exclusive: str | None = None
) -> pd.DataFrame:
    if ana_df is None or ana_df.empty:
        return pd.DataFrame()

    if month_to_exclusive is None:
        month_to_exclusive = datetime.date.today().strftime("%Y-%m")

    target_months = [m for m in sorted(ana_df["연월_키"].unique()) if month_from <= str(m) < month_to_exclusive]
    rows = []
    for m_key in target_months:
        m_real_df = ana_df[ana_df["연월_키"] == m_key]
        m_final_act = len(m_real_df)
        if m_final_act == 0:
            continue

        m_s, m_e = _month_start_end(str(m_key))
        m_total_w = get_w_days(m_s, m_e)
        t_dt = find_working_day_date(m_s, m_e, int(sel_day_num))
        if not t_dt:
            continue
        d_act = len(m_real_df[m_real_df["배송예정일_DT"].dt.date <= t_dt])
        d_30_s = t_dt - timedelta(days=30)
        d_30_w = get_w_days(d_30_s, t_dt)
        d_30_cnt = len(ana_df[(ana_df["배송예정일_DT"].dt.date >= d_30_s) & (ana_df["배송예정일_DT"].dt.date <= t_dt)])

        d_pace = d_30_cnt / d_30_w if d_30_w > 0 else 0
        d_pred = d_act + int(d_pace * (m_total_w - int(sel_day_num)))
        d_acc = max(0, min(100, (1 - abs((m_final_act - d_pred) / m_final_act)) * 100)) if m_final_act > 0 else 0
        rows.append({"연월": str(m_key), "실제결과": f"{m_final_act}건", "예측치": f"{d_pred}건", "정확도(%)": round(d_acc, 1)})

    return pd.DataFrame(rows)


def build_master_golden_summary(
    ana_df: pd.DataFrame, month_from: str = "2025-05", month_to_exclusive: str | None = None, max_day: int = 24
) -> tuple[pd.DataFrame, dict]:
    if ana_df is None or ana_df.empty:
        return pd.DataFrame(), {}

    if month_to_exclusive is None:
        month_to_exclusive = datetime.date.today().strftime("%Y-%m")
    target_months = [m for m in sorted(ana_df["연월_키"].unique()) if month_from <= str(m) < month_to_exclusive]
    if not target_months:
        return pd.DataFrame(), {}

    master_summary: dict[int, list[float]] = {}
    for m_key in target_months:
        m_real_final_df = ana_df[ana_df["연월_키"] == m_key]
        m_final_actual_cnt = len(m_real_final_df)
        m_start, m_end = _month_start_end(str(m_key))
        m_tot_w = get_w_days(m_start, m_end)

        tw = 0
        for d in pd.date_range(m_start, m_end):
            if get_w_days(d.date(), d.date()) == 0:
                continue
            tw += 1
            if tw > max_day:
                break
            d_dt = d.date()
            d_act_cnt = len(m_real_final_df[m_real_final_df["배송예정일_DT"].dt.date <= d_dt])
            d_30_s = d_dt - timedelta(days=30)
            d_30_w = get_w_days(d_30_s, d_dt)
            d_30_data_cnt = len(ana_df[(ana_df["배송예정일_DT"].dt.date >= d_30_s) & (ana_df["배송예정일_DT"].dt.date <= d_dt)])

            d_p = d_30_data_cnt / d_30_w if d_30_w > 0 else 0
            d_pred = d_act_cnt + int(d_p * (m_tot_w - tw))
            d_acc = max(0, min(100, (1 - abs((m_final_actual_cnt - d_pred) / m_final_actual_cnt)) * 100)) if m_final_actual_cnt > 0 else 0
            master_summary.setdefault(tw, []).append(d_acc)

    master_history = [{"영업일": w, "평균정확도": (sum(accs) / len(accs))} for w, accs in master_summary.items()]
    df_master = pd.DataFrame(master_history)
    meta = {"target_months": target_months}
    return df_master, meta
