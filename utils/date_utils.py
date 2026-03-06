# utils/date_utils.py
# 날짜 관련 유틸리티 함수

import pandas as pd
import holidays
from datetime import timedelta

def get_w_days(start, end):
    """
    특정 기간(start ~ end) 사이의 영업일 수 계산 (주말/한국 공휴일 제외)
    """
    kr_hols = holidays.KR()
    try:
        days = pd.date_range(start, end)
        return len([d for d in days if d.weekday() != 6 and d not in kr_hols])
    except Exception as e:
        # 날짜 범위 오류 등 예외 발생 시 0 반환
        return 0

def get_month_range(date_obj):
    """
    특정 날짜가 속한 월의 시작일과 종료일 계산
    """
    m_start = date_obj.replace(day=1)

def get_current_context():
    """
    현재 시점(KST) 기준 날짜 컨텍스트 반환
    """
    from zoneinfo import ZoneInfo
    import datetime
    
    today_kst = datetime.datetime.now(ZoneInfo("Asia/Seoul")).date()
    yesterday = today_kst - datetime.timedelta(days=1)
    
    m_key = yesterday.strftime('%Y-%m')
    m_start = yesterday.replace(day=1)
    # 다음 달 1일에서 하루 뺀 날 (이번 달 마지막 날)
    m_end = (m_start + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)
    
    yesterday_str = yesterday.strftime('%Y-%m-%d')
    
    return {
        "today": today_kst,
        "yesterday": yesterday,
        "yesterday_str": yesterday_str,
        "m_key": m_key,
        "m_start": m_start,
        "m_end": m_end
    }
