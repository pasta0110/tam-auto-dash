import pandas as pd
import re

def clean_v(v):
    v = str(v).replace('청호_', '')
    for k in ["수도권", "대전", "대구", "부산", "경남", "광주", "전주", "강원"]:
        if k in v:
            return k
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


def get_main_cat(name):
    n = str(name).upper().replace(" ", "").replace("-", "").replace("+", "").strip()
    if "매트리스" in n:
        return "매트리스"
    if "파운데이션" in n:
        return "파운데이션"
    if "프레임" in n:
        return "프레임"
    return "기타"


def check_panel(name, p_type):
    n = str(name).upper().replace(" ", "")
    return p_type in n


def process_data(delivery_df):

    df = delivery_df.copy()

    # 수량
    df['수량'] = df['상품명'].apply(get_qty)

    # 품목
    df['품목구분'] = df['상품명'].apply(get_main_cat)

    # 판넬
    df['is_판넬01'] = df['상품명'].apply(lambda x: check_panel(x, "판넬01"))
    df['is_판넬05'] = df['상품명'].apply(lambda x: check_panel(x, "판넬05"))

    # 배송사 정제
    df['배송사_정제'] = df['배송사'].apply(clean_v)

    # ⭐ 핵심 (이게 없어서 에러 발생)
    df['배송예정일_DT'] = pd.to_datetime(df['배송예정일'], errors='coerce')

    df = df.dropna(subset=['배송예정일_DT']).sort_values('배송예정일_DT')

    # 연월키
    df['연월_키'] = df['배송예정일_DT'].dt.strftime('%Y-%m')

    # 분석용 데이터
    ana_df = df[
        (df['배송상태'].astype(str).str.contains('완료|4', na=False)) &
        (df['주문유형'].str.contains('정상', na=False))
    ]

    return ana_df