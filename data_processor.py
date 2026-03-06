import pandas as pd

def process_data(df):

    # 날짜 컬럼 처리
    if "배송예정일" in df.columns:
        df["배송예정일_DT"] = pd.to_datetime(df["배송예정일"], errors="coerce")

    if "출고일" in df.columns:
        df["출고일_DT"] = pd.to_datetime(df["출고일"], errors="coerce")

    # 분석 기준 날짜 선택
    if "배송예정일_DT" in df.columns:
        base_date = df["배송예정일_DT"]
    elif "출고일_DT" in df.columns:
        base_date = df["출고일_DT"]
    else:
        base_date = None

    # 연월 키 생성
    if base_date is not None:
        df["연월_키"] = base_date.dt.strftime("%y년 %m월")

    # 배송사 정제
    if "배송사" in df.columns:
        df["배송사_정제"] = df["배송사"].astype(str).str.strip()

    return df