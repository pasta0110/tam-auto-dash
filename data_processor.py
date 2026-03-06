import pandas as pd

def process_data(df):

    df = df.copy()

    # 배송일 컬럼 찾기
    date_col = None

    for c in ["배송예정일", "배송일", "출고일"]:
        if c in df.columns:
            date_col = c
            break

    if date_col:
        df["배송예정일_DT"] = pd.to_datetime(df[date_col], errors="coerce")
        df["연월_키"] = df["배송예정일_DT"].dt.strftime("%y년 %m월")

    # 배송사 정제
    if "배송사" in df.columns:
        df["배송사_정제"] = df["배송사"].astype(str).str.strip()

    return df