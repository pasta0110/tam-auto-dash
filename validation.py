def validate_data(df):

    report = {}

    # 결측치 체크
    report["missing_values"] = df.isnull().sum().to_dict()

    # 행 개수
    report["total_rows"] = len(df)

    # 컬럼 수
    report["total_columns"] = len(df.columns)

    return report