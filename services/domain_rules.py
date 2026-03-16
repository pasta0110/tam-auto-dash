import pandas as pd


def cheongho_mask(df: pd.DataFrame) -> pd.Series:
    if "매출처" not in df.columns:
        return pd.Series(True, index=df.index)
    return df["매출처"].astype(str).str.strip().eq("청호나이스")


def filter_cheongho(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    return df[cheongho_mask(df)].copy()


def str_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col in df.columns:
        return df[col].astype(str)
    return pd.Series("", index=df.index)


def delivery_event_flags(df: pd.DataFrame) -> dict:
    """
    배송 이벤트 분류용 공통 플래그.
    """
    ship_type = str_col(df, "배송유형")
    order_type = str_col(df, "주문유형")
    order_stat = str_col(df, "주문상태")
    ship_stat = str_col(df, "배송상태")

    is_as = ship_type.eq("AS")
    is_exchange = ship_type.eq("교환")
    is_return = ship_type.isin(["반품", "회수"]) | order_type.eq("반품")
    is_cancel = ship_stat.eq("미설치") | order_stat.eq("주문취소")
    is_complete = order_stat.str.contains("완료", na=False) | ship_stat.str.contains("완료|4", na=False)
    is_normal_complete = order_type.eq("정상") & is_complete
    is_normal_strict = (
        order_type.eq("정상")
        & ~order_stat.eq("주문취소")
        & ship_type.eq("정상")
        & ~ship_stat.eq("미설치")
    )
    return {
        "is_as": is_as,
        "is_exchange": is_exchange,
        "is_return": is_return,
        "is_cancel": is_cancel,
        "is_complete": is_complete,
        "is_normal_complete": is_normal_complete,
        "is_normal_strict": is_normal_strict,
    }

