import pandas as pd

def process_data(df):

    df = df.copy()

    st.write(ana_df.columns)

    # 배송예정일 datetime 변환
    if "배송예정일" in df.columns:
        df["배송예정일_DT"] = pd.to_datetime(df["배송예정일"], errors="coerce")

    # 연월 키 생성
    if "배송예정일_DT" in df.columns:
        df["연월_키"] = df["배송예정일_DT"].dt.strftime("%y년 %m월")

    # 배송사 정제
    if "배송사" in df.columns:
        df["배송사_정제"] = df["배송사"].astype(str).str.strip()

    return df