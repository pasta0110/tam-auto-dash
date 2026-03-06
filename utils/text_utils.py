# utils/text_utils.py
# 텍스트 처리 유틸리티 함수

import re

def clean_v(v):
    """
    배송사 이름에서 지역명 추출 ('청호_수도권' -> '수도권')
    """
    v = str(v).replace('청호_', '')
    for k in ["수도권", "대전", "대구", "부산", "경남", "광주", "전주", "강원"]:
        if k in v:
            return k
    return v

def get_qty(name):
    """
    상품명에서 수량 추출 ('... 2ea' -> 2)
    """
    try:
        name = str(name).lower()
        match = re.search(r'(\d+)ea', name)
        if match:
            return int(match.group(1))
        return 1
    except:
        return 1

def get_main_cat(name):
    """
    메인 카테고리 분류 (매트리스, 파운데이션, 프레임, 기타)
    """
    n = str(name).upper().replace(" ", "").replace("-", "").replace("+", "").strip()
    if "매트리스" in n:
        return "매트리스"
    if "파운데이션" in n:
        return "파운데이션"
    if "프레임" in n:
        return "프레임"
    return "기타"

def check_panel(name, p_type):
    """
    상품명에 특정 판넬 유형이 포함되는지 확인 (불리언 반환)
    """
    n = str(name).upper().replace(" ", "")
    return p_type in n
