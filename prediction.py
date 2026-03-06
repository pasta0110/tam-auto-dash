import pandas as pd

def run_prediction(df):

    # 예시: 월별 물량 계산
    monthly = df.groupby("연월_키").size().reset_index(name="건수")

    result = {
        "monthly_data": monthly,
        "prediction": "예측 로직 자리"
    }

    return result