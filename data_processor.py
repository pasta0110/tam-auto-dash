import pandas as pd

def process_data(df):

    df = df.copy()

    # 날짜 컬럼 찾기
    date_col = None

    for c in ["배송예정일", "배송일", "출고일"]:
        if c in df.columns:
            date_col = c
            break

    # 날짜 처리
    if date_col:
        df["배송예정일_DT"] = pd.to_datetime(df[date_col], errors="coerce")

        # 월 키 (YYYY-MM)
        df["연월_키"] = df["배송예정일_DT"].dt.strftime("%Y-%m")

    # 배송사 정제
    if "배송사" in df.columns:
        df["배송사_정제"] = df["배송사"].astype(str).str.strip()

    return df