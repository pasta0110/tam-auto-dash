from __future__ import annotations

import re
import numpy as np
import pandas as pd


def mask_name(v: str) -> str:
    s = str(v or "").strip()
    if not s:
        return "-"
    if len(s) <= 1:
        return "*"
    if len(s) == 2:
        return s[0] + "*"
    return s[0] + ("*" * (len(s) - 2)) + s[-1]


def mask_addr(v: str) -> str:
    s = str(v or "").strip()
    if not s:
        return "-"
    tokens = s.split()
    if len(tokens) <= 2:
        return " ".join(tokens)
    return " ".join(tokens[:2]) + " ..."


def clean_address(addr: str) -> str:
    if not isinstance(addr, str):
        return ""
    addr = re.sub(r"\([^)]*\)", "", addr)
    addr = re.sub(r"[^\w\s]", " ", addr)
    tokens = addr.split()
    if len(tokens) >= 2:
        return " ".join(tokens[:5])
    return " ".join(tokens)


def build_delay_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    if "주문등록일" not in df.columns or "배송예정일" not in df.columns:
        return pd.DataFrame()

    tmp = df.copy()
    tmp["주문등록일"] = pd.to_datetime(tmp["주문등록일"], errors="coerce")
    tmp["배송예정일"] = pd.to_datetime(tmp["배송예정일"], errors="coerce")
    tmp = tmp.dropna(subset=["주문등록일", "배송예정일"]).copy()
    if tmp.empty:
        return pd.DataFrame()

    start_dates = tmp["주문등록일"].values.astype("datetime64[D]")
    end_dates = tmp["배송예정일"].values.astype("datetime64[D]")
    delay_days = np.busday_count(start_dates, end_dates + np.timedelta64(1, "D"))
    tmp["영업배송일수"] = np.maximum(delay_days, 0)

    carrier = tmp["배송사_정제"].astype(str)
    is_capital = carrier.str.contains("수도권|수도", regex=True)
    standard_days = np.where(is_capital, 3, 4)
    days = tmp["영업배송일수"].to_numpy()
    tmp["상태"] = np.select(
        [days <= standard_days, days <= (standard_days + 2)],
        ["green", "orange"],
        default="red",
    )
    return tmp

