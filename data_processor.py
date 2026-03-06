import pandas as pd

def process_data(df):

    # 날짜 컬럼 datetime 변환
    if "출고일" in df.columns:
        df["출고일"] = pd.to_datetime(df["출고일"], errors="coerce")

    # 연월 키 생성 (그래프용)
    if "출고일" in df.columns:
        df["연월_키"] = df["출고일"].dt.strftime("%y년 %m월")

    # 배송사 정제 (예시)
    if "배송사" in df.columns:
        df["배송사_정제"] = df["배송사"].str.strip()

    return df