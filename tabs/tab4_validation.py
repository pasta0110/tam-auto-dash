import streamlit as st
import pandas as pd
import datetime
import plotly.express as px

from config import V_ORDER
from utils.date_utils import get_w_days


def render_validation(ana_df):

    st.title("🔍 예측 모델 검증 및 골든 데이 분석")

    st.markdown(
        "전월 데이터를 바탕으로 **'몇 영업일째의 예측이 가장 정확했는지'**를 분석하여 모델의 신뢰도를 검증합니다."
    )

    # 1️⃣ 상단 컨트롤러
    c1, c2, c3 = st.columns([1.5, 1, 2])

    available_months = sorted(ana_df["연월_키"].unique(), reverse=True)
    default_idx = 1 if len(available_months) > 1 else 0

    with c1:
        sel_month_key = st.selectbox(
            "📅 검증 대상 월 선택",
            available_months,
            index=default_idx,
            key="v_month_sel",
        )

    with c2:
        sel_day_num = st.number_input(
            "📅 시뮬레이션 기준일 (영업일)",
            min_value=1,
            max_value=20,
            value=3,
            key="v_day_num",
        )

    with c3:
        st.info(
            f"💡 **분석 시나리오:** {sel_month_key}월의 **{sel_day_num}영업일차** 시점 예측치 분석"
        )

    # 2️⃣ 날짜 계산
    sel_year, sel_month = map(int, sel_month_key.split("-"))

    sim_m_start = datetime.date(sel_year, sel_month, 1)

    if sel_month == 12:
        sim_m_end = datetime.date(sel_year, 12, 31)
    else:
        sim_m_end = datetime.date(sel_year, sel_month + 1, 1) - datetime.timedelta(days=1)

    s_total_w = get_w_days(sim_m_start, sim_m_end)

    s_real_final = ana_df[ana_df["연월_키"] == sel_month_key]
    sum_actual = len(s_real_final)

    # 3️⃣ 선택 영업일 찾기
    month_days = pd.date_range(sim_m_start, sim_m_end)

    target_date = None
    w_count = 0

    for d in month_days:

        if get_w_days(d.date(), d.date()) > 0:
            w_count += 1

            if w_count == sel_day_num:
                target_date = d.date()
                break

    # 4️⃣ 예측 계산
    if target_date:

        s_act_data = ana_df[
            (ana_df["배송예정일_DT"].dt.date >= sim_m_start)
            & (ana_df["배송예정일_DT"].dt.date <= target_date)
        ]

        s_30_start = target_date - datetime.timedelta(days=30)

        s_recent_30d = ana_df[
            (ana_df["배송예정일_DT"].dt.date >= s_30_start)
            & (ana_df["배송예정일_DT"].dt.date <= target_date)
        ]

        s_recent_w = get_w_days(s_30_start, target_date)
        s_remain_w = s_total_w - sel_day_num

        test_rows = []

        sum_curr = 0
        sum_pred_rem = 0
        sum_final_pred = 0

        for v in V_ORDER:

            if v in ana_df["배송사_정제"].unique():

                v_curr = len(s_act_data[s_act_data["배송사_정제"] == v])

                v_recent = len(s_recent_30d[s_recent_30d["배송사_정제"] == v])

                v_pace = v_recent / s_recent_w if s_recent_w > 0 else 0

                v_rem_pred = int(v_pace * s_remain_w)

                v_final_pred = v_curr + v_rem_pred

                v_actual = len(s_real_final[s_real_final["배송사_정제"] == v])

                v_acc = (
                    (1 - abs((v_actual - v_final_pred) / v_actual)) * 100
                    if v_actual > 0
                    else 0
                )

                sum_curr += v_curr
                sum_pred_rem += v_rem_pred
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

        total_acc = (
            (1 - abs((sum_actual - sum_final_pred) / sum_actual)) * 100
            if sum_actual > 0
            else 0
        )

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

        st.subheader(f"📍 {sel_day_num}영업일차 예측 결과")

        st.table(pd.DataFrame(test_rows).set_index("지역센터"))

        st.divider()

        # 5️⃣ 골든데이 분석
        st.subheader(f"🏆 {sel_month_key} 예측 골든 데이 분석")

        acc_history = []

        best_acc = -1
        best_day_info = {}

        temp_w_count = 0

        for d in month_days:

            if get_w_days(d.date(), d.date()) == 0:
                continue

            temp_w_count += 1

            if temp_w_count > 12:
                break

            d_date = d.date()

            d_act = len(
                ana_df[
                    (ana_df["배송예정일_DT"].dt.date >= sim_m_start)
                    & (ana_df["배송예정일_DT"].dt.date <= d_date)
                ]
            )

            d_30_s = d_date - datetime.timedelta(days=30)

            d_30_data = ana_df[
                (ana_df["배송예정일_DT"].dt.date >= d_30_s)
                & (ana_df["배송예정일_DT"].dt.date <= d_date)
            ]

            d_30_w = get_w_days(d_30_s, d_date)

            d_pace = len(d_30_data) / d_30_w if d_30_w > 0 else 0

            d_pred = d_act + int(d_pace * (s_total_w - temp_w_count))

            d_acc = (
                (1 - abs((sum_actual - d_pred) / sum_actual)) * 100
                if sum_actual > 0
                else 0
            )

            acc_history.append(
                {
                    "영업일": f"{temp_w_count}일차",
                    "정확도": d_acc,
                }
            )

            if d_acc > best_acc:
                best_acc = d_acc
                best_day_info = {"day": temp_w_count, "acc": d_acc}

        if best_day_info:

            m1, m2 = st.columns([1, 2])

            with m1:

                st.metric(
                    "최적 예측 시점",
                    f"{best_day_info['day']}영업일",
                )

                st.metric(
                    "최고 정확도",
                    f"{best_day_info['acc']:.1f}%",
                )

            with m2:

                df_hist = pd.DataFrame(acc_history)

                fig = px.bar(
                    df_hist,
                    x="영업일",
                    y="정확도",
                    text=df_hist["정확도"].apply(lambda x: f"{x:.1f}%"),
                    color="정확도",
                    color_continuous_scale="Blues",
                )

                fig.update_layout(showlegend=False)

                st.plotly_chart(fig, use_container_width=True)

            st.success(
                f"📊 인사이트: **{best_day_info['day']}영업일차** 예측이 가장 정확했습니다."
            )