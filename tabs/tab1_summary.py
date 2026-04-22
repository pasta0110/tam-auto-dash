# tabs/tab1_summary.py
# 1. 종합 현황 (주문, 출고, 반품, 정산)

import streamlit as st
import pandas as pd
from utils.date_utils import get_w_days
from services.tab1_summary_ops import (
    safe_to_datetime,
    to_date,
    filter_order_for_tab1,
    filter_delivery_for_tab1,
    ana_df_for_tab1,
    split_month_day_df,
    build_main_rows,
    build_panel_rows,
    MAIN_PRODUCT_ROWS,
    product_metric,
)


def render(order_df, delivery_df, ana_df, ctx):
    """
    종합 현황 탭 렌더링
    Args:
        order_df: 전체 주문 데이터
        delivery_df: 전체 배송 데이터 (반품 포함)
        ana_df: 분석용 정상 완료 데이터
        ctx: 날짜 컨텍스트 (어제, 이번달 등)
    """
    
    st.title("🏛️ 청호나이스 종합 현황")
    mobile_mode = bool(st.session_state.get("ui_mobile_mode", str(st.query_params.get("mobile", "0")) == "1"))
    if mobile_mode:
        st.caption("모바일 최적화 모드: 표를 세로 배치로 표시")

    # Tab1은 morning_all_in_one_v6_final.py의 주문/출고 필터 기준을 적용한 데이터로만 계산합니다.
    order_df = filter_order_for_tab1(order_df)
    delivery_df = filter_delivery_for_tab1(delivery_df)
    ana_df = ana_df_for_tab1(delivery_df)
    
    yesterday = ctx["yesterday"]
    yesterday_str = ctx["yesterday_str"]
    m_key = ctx["m_key"]
    y_date = to_date(yesterday)
    date_header = f"기준일({y_date.strftime('%m/%d')})"
    
    if mobile_mode:
        sections = [st.container(), st.container(), st.container(), st.container()]
    else:
        col1, col2 = st.columns(2)
        col3, col4 = st.columns(2)
        sections = [col1, col2, col3, col4]
    
    # --- 1. 주문 현황 ---
    with sections[0]:
        st.subheader("🛒 1. 주문 현황")
        order_date_col = '등록일' if '등록일' in order_df.columns else order_df.columns[0]
        
        # 날짜 필터링
        # 엑셀 보고서 기준: 당월 1일 ~ 기준일(=어제)까지
        curr_order, day_order = split_month_day_df(order_df, order_date_col, y_date, m_key, yesterday_str)
        df_order = build_main_rows(curr_order, day_order, date_header)
        df_p_order = build_panel_rows(curr_order, day_order, date_header, "▶ 판넬 합계")
        
        v = pd.concat([df_order, df_p_order], ignore_index=True).set_index('품목')
        if mobile_mode:
            st.dataframe(v.reset_index(), use_container_width=True, hide_index=True, height=280)
        else:
            st.table(v)
        
    # --- 2. 출고 현황 ---
    with sections[1]:
        st.subheader("🚚 2. 출고 현황")
        # 엑셀 보고서 기준: 당월 1일 ~ 기준일(=어제)까지
        if '배송예정일_DT' in ana_df.columns:
            deli_dt = ana_df['배송예정일_DT']
        else:
            deli_dt = safe_to_datetime(ana_df['배송예정일']) if '배송예정일' in ana_df.columns else pd.Series([], dtype="datetime64[ns]")

        if deli_dt.notna().any():
            month_start = pd.Timestamp(year=y_date.year, month=y_date.month, day=1)
            monthly_delivery = ana_df[(deli_dt >= month_start) & (deli_dt.dt.date <= y_date)].copy()
            day_delivery = ana_df[deli_dt.dt.date == y_date].copy()
        else:
            monthly_delivery = ana_df[ana_df['연월_키'] == m_key]
            day_delivery = monthly_delivery[monthly_delivery['배송예정일'].astype(str).str.contains(yesterday_str, na=False)]
        
        rows = []
        for cat in MAIN_PRODUCT_ROWS:
            rows.append({
                '품목': cat,
                '당월 합계': product_metric(monthly_delivery, cat),
                date_header: product_metric(day_delivery, cat),
            })
        
        df_delivery = pd.DataFrame(rows)
        df_delivery.loc[len(df_delivery)] = [
            '합계',
            product_metric(monthly_delivery, '매트리스 계') + product_metric(monthly_delivery, '파운데이션') + product_metric(monthly_delivery, '프레임'),
            product_metric(day_delivery, '매트리스 계') + product_metric(day_delivery, '파운데이션') + product_metric(day_delivery, '프레임'),
        ]
        
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
        
        v = pd.concat([df_delivery, df_p_del], ignore_index=True).set_index('품목')
        if mobile_mode:
            st.dataframe(v.reset_index(), use_container_width=True, hide_index=True, height=280)
        else:
            st.table(v)
        
    # --- 3. 반품 현황 ---
    with sections[2]:
        st.subheader("🔄 3. 반품 현황")
        
        # 반품 완료이면서 주문유형에 '반품'이 포함된 건
        status_col = '배송상태' if '배송상태' in delivery_df.columns else 'delivery_stat_nm'
        ord_date_col = '주문등록일' if '주문등록일' in delivery_df.columns else ('등록일' if '등록일' in delivery_df.columns else 'ord_date')
        
        ret_done_df = delivery_df[
            (delivery_df[status_col].astype(str).str.contains('4|완료', na=False)) & 
            (delivery_df['주문유형'].str.contains('반품', na=False)) &
            (delivery_df['연월_키'] == m_key)
        ].copy()
        
        ret_done_df[ord_date_col] = pd.to_datetime(ret_done_df[ord_date_col], errors='coerce')
        standard_date = pd.to_datetime(m_key + "-01")
        
        # 당월주문 반품 vs 이전주문 반품 구분
        m_ret_f = ret_done_df[ret_done_df[ord_date_col] >= standard_date]
        p_ret_f = ret_done_df[(ret_done_df[ord_date_col] < standard_date) | (ret_done_df[ord_date_col].isna())]
        
        rows_ret = []
        for cat in MAIN_PRODUCT_ROWS:
            m_qty = product_metric(m_ret_f, cat)
            p_qty = product_metric(p_ret_f, cat)
            rows_ret.append({'품목': cat, '당월주문 반품': m_qty, '이전주문 반품': p_qty, '합계': m_qty + p_qty})
            
        df_ret = pd.DataFrame(rows_ret)
        df_ret.loc[len(df_ret)] = [
            '📌 합계',
            product_metric(m_ret_f, '매트리스 계') + product_metric(m_ret_f, '파운데이션') + product_metric(m_ret_f, '프레임'),
            product_metric(p_ret_f, '매트리스 계') + product_metric(p_ret_f, '파운데이션') + product_metric(p_ret_f, '프레임'),
            (
                product_metric(m_ret_f, '매트리스 계') + product_metric(m_ret_f, '파운데이션') + product_metric(m_ret_f, '프레임')
                + product_metric(p_ret_f, '매트리스 계') + product_metric(p_ret_f, '파운데이션') + product_metric(p_ret_f, '프레임')
            ),
        ]
        
        # 판넬 반품
        p_rows_ret = []
        for p_num in ['01', '05']:
            col_name = f'is_판넬{p_num}'
            m_qty = int(m_ret_f[m_ret_f[col_name] == True]['수량'].sum())
            p_qty = int(p_ret_f[p_ret_f[col_name] == True]['수량'].sum())
            
            p_rows_ret.append({'품목': f'판넬{p_num}', '당월주문 반품': m_qty, '이전주문 반품': p_qty, '합계': m_qty + p_qty})
            
        df_p_ret = pd.DataFrame(p_rows_ret)
        df_p_ret.loc[len(df_p_ret)] = ['▶ 판넬 합계', df_p_ret['당월주문 반품'].sum(), df_p_ret['이전주문 반품'].sum(), df_p_ret['합계'].sum()]
        
        v = pd.concat([df_ret, df_p_ret], ignore_index=True).set_index('품목')
        if mobile_mode:
            st.dataframe(v.reset_index(), use_container_width=True, hide_index=True, height=300)
        else:
            st.table(v)
        
    # --- 4. 최종 정산 ---
    with sections[3]:
        st.subheader("💰 4. 최종 정산")
        
        calc_rows = []
        for cat in MAIN_PRODUCT_ROWS:
            d_qty = product_metric(monthly_delivery, cat)
            r_qty = product_metric(ret_done_df, cat)
            calc_rows.append({
                '품목': cat,
                '정상 출고': d_qty,
                '반품 완료': r_qty,
                '최종 정산': d_qty - r_qty
            })
            
        df_calc = pd.DataFrame(calc_rows)
        df_calc.loc[len(df_calc)] = [
            '💰 총계', 
            product_metric(monthly_delivery, '매트리스 계') + product_metric(monthly_delivery, '파운데이션') + product_metric(monthly_delivery, '프레임'),
            product_metric(ret_done_df, '매트리스 계') + product_metric(ret_done_df, '파운데이션') + product_metric(ret_done_df, '프레임'),
            (
                product_metric(monthly_delivery, '매트리스 계') + product_metric(monthly_delivery, '파운데이션') + product_metric(monthly_delivery, '프레임')
                - (product_metric(ret_done_df, '매트리스 계') + product_metric(ret_done_df, '파운데이션') + product_metric(ret_done_df, '프레임'))
            ),
        ]
        
        # 판넬 정산
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
        
        v = pd.concat([df_calc, df_p_calc], ignore_index=True).set_index('품목')
        if mobile_mode:
            st.dataframe(v.reset_index(), use_container_width=True, hide_index=True, height=300)
        else:
            st.table(v)
