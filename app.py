import streamlit as st
import pandas as pd
import datetime
import plotly.express as px
import holidays
import requests
from io import BytesIO
from geopy.geocoders import Nominatim
from streamlit_folium import folium_static
import folium
from folium.plugins import MarkerCluster
from zoneinfo import ZoneInfo
import re

# 1. 페이지 설정
st.set_page_config(page_title="청호나이스 현황판", layout="wide", page_icon="📊")

st.markdown("""
    <style>
    /* 전체 표 공통 설정 */
    th, td { text-align: center !important; vertical-align: middle !important; }
    .stTable td { text-align: center !important; }
    
    /* 헤더 스타일 */
    thead tr th { 
        background-color: #f0f2f6 !important; 
        color: #31333F !important; 
    }

    /* 🌟 [강력 강조] 메인 '합계' 또는 '총계' 행 */
    tr:has(th:contains("합계")), tr:has(td:contains("합계")),
    tr:has(th:contains("총계")), tr:has(td:contains("총계")) {
        background-color: #3d3d3d !important;
        font-weight: bold !important;
    }
    /* 글자색 흰색 고정 */
    tr:has(th:contains("합계")) th, tr:has(td:contains("합계")) td,
    tr:has(th:contains("총계")) th, tr:has(td:contains("총계")) td {
        color: #FFFFFF !important;
    }

    /* 🌟 [은은한 강조] '판넬' 단어가 포함된 합계 행 */
    tr:has(th:contains("판넬")), tr:has(td:contains("판넬")) {
        background-color: #e9ecef !important;
        font-weight: bold !important;
    }
    /* 글자색 검은색 고정 */
    tr:has(th:contains("판넬")) th, tr:has(td:contains("판넬")) td {
        color: #31333F !important;
    }

    /* 모바일 기기 보정 */
    @media (max-width: 640px) {
        .stTable { font-size: 12px !important; }
    }
    
    /* 상단 탭 글자 크기 조정 */
    button[data-baseweb="tab"] { font-size: 16px !important; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# 🛠️ 영업일 계산 함수
def get_w_days(start, end):
    kr_hols = holidays.KR()
    days = pd.date_range(start, end)
    return len([d for d in days if d.weekday() != 6 and d not in kr_hols])

# 2. 데이터 불러오기
DATA_URL = "https://github.com/pasta0110/tam-auto-dash/raw/refs/heads/main/data.xlsx"

@st.cache_data(ttl=300)
def load_data():
    try:
        response = requests.get(DATA_URL, timeout=15)
        response.raise_for_status()
        with BytesIO(response.content) as f:
            ord_df = pd.read_excel(f, sheet_name='주문건')
            f.seek(0)
            del_df = pd.read_excel(f, sheet_name='출고건', skiprows=13)
        ord_df.columns = [str(c).strip() for c in ord_df.columns]
        del_df.columns = [str(c).strip() for c in del_df.columns]
        return ord_df, del_df
    except Exception as e:
        st.error(f"⚠️ 데이터 로딩 실패: {e}")
        return None, None

def clean_v(v):
    v = str(v).replace('청호_', '')
    for k in ["수도권", "대전", "대구", "부산", "경남", "광주", "전주", "강원"]:
        if k in v: return k
    return v

def get_qty(name):
    try:
        name = str(name).lower()
        match = re.search(r'(\d+)ea', name)
        if match:
            return int(match.group(1))
        return 1
    except:
        return 1

# 🛠️ [수정] 메인 카테고리 분류 (프레임 내 판넬 포함 허용)
def get_main_cat(name):
    n = str(name).upper().replace(" ", "").replace("-", "").replace("+", "").strip()
    if "매트리스" in n: return "매트리스"
    if "파운데이션" in n: return "파운데이션"
    if "프레임" in n: return "프레임"
    return "기타"

# 🛠️ [수정] 판넬 여부 독립 판정 함수
def check_panel(name, p_type):
    n = str(name).upper().replace(" ", "")
    return p_type in n

order_df, delivery_df = load_data()

if order_df is not None and delivery_df is not None:
    # --- 기본 설정 (KST 기준) --- 
    today_kst = datetime.datetime.now(ZoneInfo("Asia/Seoul")).date()
    yesterday = today_kst - datetime.timedelta(days=1)

    y_str, m_key = yesterday.strftime('%Y-%m-%d'), yesterday.strftime('%Y-%m')
    m_start = yesterday.replace(day=1)
    m_end = (m_start + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)
    
    status_col = '배송상태' if '배송상태' in delivery_df.columns else 'delivery_stat_nm'
    ord_date_col = '주문등록일' if '주문등록일' in delivery_df.columns else ('등록일' if '등록일' in delivery_df.columns else 'ord_date')
    V_ORDER = ["수도권", "대전", "대구", "부산", "경남", "광주", "전주", "강원"]

    total_w = get_w_days(m_start, m_end)
    passed_w = get_w_days(m_start, yesterday)
    remain_w = total_w - passed_w

    # --- 데이터 정제 (중복 집계 로직 반영) ---
    for df in [order_df, delivery_df]:
        df['수량'] = df['상품명'].apply(get_qty)
        df['품목구분'] = df['상품명'].apply(get_main_cat)
        # 판넬 독립 집계를 위한 불리언 컬럼 생성
        df['is_판넬01'] = df['상품명'].apply(lambda x: check_panel(x, "판넬01"))
        df['is_판넬05'] = df['상품명'].apply(lambda x: check_panel(x, "판넬05"))
    
    delivery_df['배송사_정제'] = delivery_df['배송사'].apply(clean_v)
    delivery_df['배송예정일_DT'] = pd.to_datetime(delivery_df['배송예정일'], errors='coerce')
    delivery_df = delivery_df.dropna(subset=['배송예정일_DT']).sort_values('배송예정일_DT')
    delivery_df['연월_키'] = delivery_df['배송예정일_DT'].dt.strftime('%Y-%m')

    # 완료(4) & 정상 건 필터링
    ana_df = delivery_df[(delivery_df['배송상태'].astype(str).str.contains('완료|4', na=False)) & (delivery_df['주문유형'].str.contains('정상', na=False))]

    # 탭 구성
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📋 1. 종합 현황", "📈 2. 배송사별 분석", "🚀 3. 당월 출고 예측", "🔍 4. 예측 모델 검증", "📍 5. 배송 지도"])

    # --- TAB 1: 종합 현황 ---
with tab1:
    st.title("🏛️ 청호나이스 종합 현황")
    yesterday_str = yesterday.strftime('%Y-%m-%d')
    date_header = f"기준일({yesterday.strftime('%m/%d')})" 

    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)

    # 1. 주문 현황
    with col1:
        st.subheader("🛒 1. 주문 현황")
        order_date_col = '등록일' if '등록일' in order_df.columns else order_df.columns[0]
        curr_order = order_df[order_df[order_date_col].astype(str).str.contains(m_key, na=False)]
        day_order = curr_order[curr_order[order_date_col].astype(str).str.contains(yesterday_str, na=False)]

        rows = []
        for cat in ['매트리스', '파운데이션', '프레임']:
            if cat == '프레임':
                # ✅ 프레임은 건수 기준
                rows.append({
                    '품목': cat,
                    '당월 합계': curr_order[curr_order['품목구분'] == cat].shape[0],
                    date_header: day_order[day_order['품목구분'] == cat].shape[0]
                })
            else:
                # ✅ 매트리스/파운데이션은 수량 기준
                rows.append({
                    '품목': cat,
                    '당월 합계': int(curr_order[curr_order['품목구분'] == cat]['수량'].sum()),
                    date_header: int(day_order[day_order['품목구분'] == cat]['수량'].sum())
                })
        df_order = pd.DataFrame(rows)
        df_order.loc[len(df_order)] = ['합계', df_order['당월 합계'].sum(), df_order[date_header].sum()]

        # ✅ 판넬은 독립적으로 수량 기준 집계
        p_rows = []
        for p_num in ['01', '05']:
            col_name = f'is_판넬{p_num}'
            p_rows.append({
                '품목': f'판넬{p_num}',
                '당월 합계': int(curr_order[curr_order[col_name] == True]['수량'].sum()),
                date_header: int(day_order[day_order[col_name] == True]['수량'].sum())
            })
        df_p_order = pd.DataFrame(p_rows)
        df_p_order.loc[len(df_p_order)] = ['▶ 판넬 합계', df_p_order['당월 합계'].sum(), df_p_order[date_header].sum()]
        st.table(pd.concat([df_order, df_p_order], ignore_index=True).set_index('품목'))

    # 2. 출고 현황
    with col2:
        st.subheader("🚚 2. 출고 현황")
        monthly_delivery = ana_df[ana_df['연월_키'] == m_key]
        day_delivery = monthly_delivery[monthly_delivery['배송예정일'].astype(str).str.contains(yesterday_str, na=False)]

        rows = []
        for cat in ['매트리스', '파운데이션', '프레임']:
            if cat == '프레임':
                rows.append({
                    '품목': cat,
                    '당월 합계': monthly_delivery[monthly_delivery['품목구분'] == cat].shape[0],
                    date_header: day_delivery[day_delivery['품목구분'] == cat].shape[0]
                })
            else:
                rows.append({
                    '품목': cat,
                    '당월 합계': int(monthly_delivery[monthly_delivery['품목구분'] == cat]['수량'].sum()),
                    date_header: int(day_delivery[day_delivery['품목구분'] == cat]['수량'].sum())
                })
        df_delivery = pd.DataFrame(rows)
        df_delivery.loc[len(df_delivery)] = ['합계', df_delivery['당월 합계'].sum(), df_delivery[date_header].sum()]

        p_rows = []
        for p_num in ['01', '05']:
            col_name = f'is_판넬{p_num}'
            p_rows.append({
                '품목': f'판넬{p_num}',
                '당월 합계': int(monthly_delivery[monthly_delivery[col_name] == True]['수량'].sum()),
                date_header: int(day_delivery[day_delivery[col_name] == True]['수량'].sum())
            })
        df_p_del = pd.DataFrame(p_rows)
        df_p_del.loc[len(df_p_del)] = ['▶ 판넬 합계', df_p_del['당월 합계'].sum(), df_p_del[date_header].sum()]
        st.table(pd.concat([df_delivery, df_p_del], ignore_index=True).set_index('품목'))

    # 3. 반품 현황
    with col3:
        st.subheader("🔄 3. 반품 현황")
        ret_done_df = delivery_df[
            (delivery_df[status_col].astype(str).str.contains('4|완료', na=False)) &
            (delivery_df['주문유형'].str.contains('반품', na=False)) &
            (delivery_df['연월_키'] == m_key)
        ].copy()

        ret_done_df[ord_date_col] = pd.to_datetime(ret_done_df[ord_date_col], errors='coerce')
        standard_date = pd.to_datetime(m_key + "-01")
        m_ret_f = ret_done_df[ret_done_df[ord_date_col] >= standard_date]
        p_ret_f = ret_done_df[(ret_done_df[ord_date_col] < standard_date) | (ret_done_df[ord_date_col].isna())]

        rows_ret = []
        for cat in ['매트리스', '파운데이션', '프레임']:
            if cat == '프레임':
                m_qty = m_ret_f[m_ret_f['품목구분'] == cat].shape[0]
                p_qty = p_ret_f[p_ret_f['품목구분'] == cat].shape[0]
            else:
                m_qty = int(m_ret_f[m_ret_f['품목구분'] == cat]['수량'].sum())
                p_qty = int(p_ret_f[p_ret_f['품목구분'] == cat]['수량'].sum())
            rows_ret.append({'품목': cat, '당월주문 반품': m_qty, '이전주문 반품': p_qty, '합계': m_qty + p_qty})
        df_ret = pd.DataFrame(rows_ret)
        df_ret.loc[len(df_ret)] = ['📌 합계', df_ret['당월주문 반품'].sum(), df_ret['이전주문 반품'].sum(), df_ret['합계'].sum()]

        p_rows_ret = []
        for p_num in ['01', '05']:
            col_name = f'is_판넬{p_num}'
            m_qty = int(m_ret_f[m_ret_f[col_name] == True]['수량'].sum())
            p_qty = int(p_ret_f[p_ret_f[col_name] == True]['수량'].sum())
            p_rows_ret.append({'품목': f'판넬{p_num}', '당월주문 반품': m_qty, '이전주문 반품': p_qty, '합계': m_qty + p_qty})
        df_p_ret = pd.DataFrame(p_rows_ret)
        df_p_ret.loc[len(df_p_ret)] = ['▶ 판넬 합계', df_p_ret['당월주문 반품'].sum(), df_p_ret['이전주문 반품'].sum(), df_p_ret['합계'].sum()]
        st.table(pd.concat([df_ret, df_p_ret], ignore_index=True).set_index('품목'))

    # 4. 최종 정산 수량
with col4:
    st.subheader("💰 4. 최종 정산")

    # 메인 품목 및 총계
    calc_rows = []
    for cat in ['매트리스', '파운데이션', '프레임']:
        if cat == '프레임':
            # ✅ 프레임은 건수 기준
            d_qty = monthly_delivery[monthly_delivery['품목구분'] == cat].shape[0]
            r_qty = ret_done_df[ret_done_df['품목구분'] == cat].shape[0]
        else:
            # ✅ 매트리스/파운데이션은 수량 기준
            d_qty = int(monthly_delivery[monthly_delivery['품목구분'] == cat]['수량'].sum())
            r_qty = int(ret_done_df[ret_done_df['품목구분'] == cat]['수량'].sum())

        calc_rows.append({
            '품목': cat,
            '정상 출고': d_qty,
            '반품 완료': r_qty,
            '최종 정산': d_qty - r_qty
        })

    df_calc = pd.DataFrame(calc_rows)
    df_calc.loc[len(df_calc)] = [
        '💰 총계',
        df_calc['정상 출고'].sum(),
        df_calc['반품 완료'].sum(),
        df_calc['최종 정산'].sum()
    ]

    # ✅ 판넬은 독립적으로 수량 기준 집계
    p_calc_rows = []
    for p_num in ['01', '05']:
        col_name = f'is_판넬{p_num}'
        d_qty = int(monthly_delivery[monthly_delivery[col_name] == True]['수량'].sum())
        r_qty = int(ret_done_df[ret_done_df[col_name] == True]['수량'].sum())
        p_calc_rows.append({
            '품목': f'판넬{p_num}',
            '정상 출고': d_qty,
            '반품 완료': r_qty,
            '최종 정산': d_qty - r_qty
        })

    df_p_calc = pd.DataFrame(p_calc_rows)
    df_p_calc.loc[len(df_p_calc)] = [
        '📦 판넬 총계',
        df_p_calc['정상 출고'].sum(),
        df_p_calc['반품 완료'].sum(),
        df_p_calc['최종 정산'].sum()
    ]

    st.table(pd.concat([df_calc, df_p_calc], ignore_index=True).set_index('품목'))


    # --- TAB 3: 당월 출고 예측 ---
    with tab3:
        st.title("🚀 당월 출고 최종 예측 (최근 30일 페이스)")
        m_start = yesterday.replace(day=1)
        m_end = (m_start + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)
        total_w = get_w_days(m_start, m_end)
        passed_w = get_w_days(m_start, yesterday)
        remain_w = total_w - passed_w
        
        last_30_days_start = yesterday - datetime.timedelta(days=30)
        recent_30d_data = ana_df[(ana_df['배송예정일_DT'] >= pd.to_datetime(last_30_days_start)) & (ana_df['배송예정일_DT'] <= pd.to_datetime(yesterday))]
        recent_working_days = get_w_days(last_30_days_start, yesterday)
        
        st.info(f"💡 최근 30일 영업일 {recent_working_days}일의 실적을 반영하여 남은 {remain_w}일간의 물량을 예측합니다.")
        sum_curr, sum_avg, sum_remain, sum_total = 0, 0.0, 0, 0
        pred_rows = []
        for v in V_ORDER:
            if v in ana_df['배송사_정제'].unique():
                curr_act = len(ana_df[(ana_df['배송사_정제'] == v) & (ana_df['연월_키'] == m_key)])
                v_recent_count = len(recent_30d_data[recent_30d_data['배송사_정제'] == v])
                avg_30d = v_recent_count / recent_working_days if recent_working_days > 0 else 0
                rem_pred = int(avg_30d * remain_w)
                projected = curr_act + rem_pred
                sum_curr += curr_act
                sum_avg += avg_30d
                sum_remain += rem_pred
                sum_total += projected
                pred_rows.append({'배송사': v, '현재 실적(당월)': f"{curr_act} 건", '최근 30일 평균': f"{avg_30d:.1f} 건/일", f'남은 영업일 예상({remain_w}일)': f"{rem_pred} 건", '당월 최종 예측': f"{projected} 건"})
        pred_rows.append({'배송사': '📌 합계', '현재 실적(당월)': f"{sum_curr} 건", '최근 30일 평균': f"{sum_avg:.1f} 건/일", f'남은 영업일 예상({remain_w}일)': f"{sum_remain} 건", '당월 최종 예측': f"{sum_total} 건"})
        st.subheader("📍 지역별 출고 예측")
        st.table(pd.DataFrame(pred_rows).set_index('배송사'))

    st.caption(f"최종 업데이트: {yesterday_str} | 영업일 기준: 월~토(공휴일 제외) | 배송상태 '완료' 집계")


# --- TAB 4: 예측 모델 검증 (탬버쌤의 원본 로직 완벽 복구) ---
    with tab4:
        st.title("🔍 예측 모델 검증 및 골든 데이 분석")
        st.markdown("전월 데이터를 바탕으로 **'몇 영업일째의 예측이 가장 정확했는지'**를 분석하여 모델의 신뢰도를 검증합니다.")
        
        # 1. 상단 컨트롤러
        c1, c2, c3 = st.columns([1.5, 1, 2])
        available_months = sorted(ana_df['연월_키'].unique(), reverse=True)
        default_idx = 1 if len(available_months) > 1 else 0
        
        with c1:
            sel_month_key = st.selectbox("📅 검증 대상 월 선택", available_months, index=default_idx, key="v_month_sel")
        with c2:
            sel_day_num = st.number_input("📅 시뮬레이션 기준일 (영업일)", min_value=1, max_value=20, value=3, key="v_day_num")
        with c3:
            st.info(f"💡 **분석 시나리오:** {sel_month_key}월의 **{sel_day_num}영업일차** 시점 예측치 분석")

        # 2. 날짜 및 기초 데이터 설정
        sel_year, sel_month = map(int, sel_month_key.split('-'))
        sim_m_start = datetime.date(sel_year, sel_month, 1)
        # 말일 계산 (안전하게)
        if sel_month == 12: sim_m_end = datetime.date(sel_year, 12, 31)
        else: sim_m_end = datetime.date(sel_year, sel_month + 1, 1) - datetime.timedelta(days=1)
        
        s_total_w = get_w_days(sim_m_start, sim_m_end)
        s_real_final = ana_df[ana_df['연월_키'] == sel_month_key]
        sum_actual = len(s_real_final)

        # 3. 선택한 영업일 날짜 찾기 (화면 안나오던 원인 해결용 로직)
        month_days = pd.date_range(sim_m_start, sim_m_end)
        target_date = None
        w_count = 0
        for d in month_days:
            if get_w_days(d.date(), d.date()) > 0:
                w_count += 1
                if w_count == sel_day_num:
                    target_date = d.date()
                    break
        
        # 🌟 실제 화면을 그리는 핵심 블록
        if target_date:
            # 날짜 비교 시 .dt.date로 형식을 맞춰야 에러가 안 납니다.
            s_act_data = ana_df[(ana_df['배송예정일_DT'].dt.date >= sim_m_start) & (ana_df['배송예정일_DT'].dt.date <= target_date)]
            s_30_start = target_date - datetime.timedelta(days=30)
            s_recent_30d = ana_df[(ana_df['배송예정일_DT'].dt.date >= s_30_start) & (ana_df['배송예정일_DT'].dt.date <= target_date)]
            s_recent_w = get_w_days(s_30_start, target_date)
            s_remain_w = s_total_w - sel_day_num

            test_rows = []
            sum_curr, sum_recent_cnt, sum_pred_rem, sum_final_pred = 0, 0, 0, 0

            for v in V_ORDER:
                if v in ana_df['배송사_정제'].unique():
                    v_curr = len(s_act_data[s_act_data['배송사_정제'] == v])
                    v_recent = len(s_recent_30d[s_recent_30d['배송사_정제'] == v])
                    v_pace = v_recent / s_recent_w if s_recent_w > 0 else 0
                    v_rem_pred = int(v_pace * s_remain_w)
                    v_final_pred = v_curr + v_rem_pred
                    v_actual = len(s_real_final[s_real_final['배송사_정제'] == v])
                    
                    v_acc = (1 - abs((v_actual - v_final_pred)/v_actual)) * 100 if v_actual > 0 else 0
                    
                    sum_curr += v_curr; sum_recent_cnt += v_recent; 
                    sum_pred_rem += v_rem_pred; sum_final_pred += v_final_pred

                    test_rows.append({
                        '지역센터': v, '당시 실적': f"{v_curr}건", '일평균 페이스': f"{v_pace:.1f}건/일",
                        '예측 최종': f"{v_final_pred}건", '실제 결과': f"{v_actual}건", '정확도': f"{v_acc:.1f}%"
                    })

            total_acc = (1 - abs((sum_actual - sum_final_pred)/sum_actual)) * 100 if sum_actual > 0 else 0
            test_rows.append({
                '지역센터': '📌 합계', '당시 실적': f"{sum_curr}건", '일평균 페이스': '-',
                '예측 최종': f"{sum_final_pred}건", '실제 결과': f"{sum_actual}건", '정확도': f"{total_acc:.1f}%"
            })
            
            st.subheader(f"📍 {sel_day_num}영업일차({target_date.strftime('%m/%d')}) 예측 결과")
            st.table(pd.DataFrame(test_rows).set_index('지역센터'))

            st.divider()

            # 4. 🏆 [탬버쌤의 하이라이트] 골든 데이 분석
            st.subheader(f"🏆 {sel_month_key} 예측 골든 데이 분석 (1~12 영업일)")
            
            acc_history = []
            best_acc = -1
            best_day_info = {}

            temp_w_count = 0
            for d in month_days:
                if get_w_days(d.date(), d.date()) == 0: continue
                temp_w_count += 1
                if temp_w_count > 12: break # 12영업일 확장 분석
                
                d_date = d.date()
                d_act = len(ana_df[(ana_df['배송예정일_DT'].dt.date >= sim_m_start) & (ana_df['배송예정일_DT'].dt.date <= d_date)])
                d_30_s = d_date - datetime.timedelta(days=30)
                d_30_data = ana_df[(ana_df['배송예정일_DT'].dt.date >= d_30_s) & (ana_df['배송예정일_DT'].dt.date <= d_date)]
                d_30_w = get_w_days(d_30_s, d_date)
                
                d_pace = len(d_30_data) / d_30_w if d_30_w > 0 else 0
                d_pred = d_act + int(d_pace * (s_total_w - temp_w_count))
                d_acc = (1 - abs((sum_actual - d_pred)/sum_actual)) * 100 if sum_actual > 0 else 0
                
                acc_history.append({"영업일": f"{temp_w_count}일차", "날짜": d_date.strftime('%m/%d'), "정확도": d_acc})
                if d_acc > best_acc:
                    best_acc = d_acc
                    best_day_info = {"day": temp_w_count, "date": d_date.strftime('%m/%d'), "acc": d_acc}

            # 🌟 [Metric & Chart 표시]
            if best_day_info:
                m1, m2 = st.columns([1, 2])
                with m1:
                    st.metric("최적 예측 시점", f"{best_day_info['day']}영업일", f"{best_day_info['date']}")
                    st.metric("최고 정확도", f"{best_day_info['acc']:.1f}%")
                with m2:
                    df_hist = pd.DataFrame(acc_history)
                    # 탬버쌤이 원하셨던 바 차트
                    fig_hist = px.bar(df_hist, x='영업일', y='정확도', text=df_hist['정확도'].apply(lambda x: f"{x:.1f}%"),
                                     title=f"{sel_month_key} 영업일별 정확도 추이", color='정확도', color_continuous_scale='Blues')
                    fig_hist.update_layout(yaxis_range=[min(df_hist['정확도'])-5, 100], showlegend=False)
                    st.plotly_chart(fig_hist, use_container_width=True)

                st.success(f"📊 **인사이트:** {sel_month_key}월 분석 결과, **{best_day_info['day']}영업일차**에 예측한 수치가 가장 정확했습니다.")
        else:
            st.warning("영업일 데이터를 계산할 수 없습니다.")