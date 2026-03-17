from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ContractResult:
    ok: bool
    missing: list[str]
    name: str


RAW_ORDER_REQUIRED = {"주문번호", "상품명"}
RAW_DELIVERY_REQUIRED = {"주문번호", "상품명", "배송예정일", "주문유형"}


def validate_required_columns(df: pd.DataFrame | None, required: set[str], name: str) -> ContractResult:
    if df is None:
        return ContractResult(False, sorted(required), name)
    cols = set(df.columns)
    missing = sorted(list(required - cols))
    return ContractResult(len(missing) == 0, missing, name)


def validate_raw_inputs(order_df: pd.DataFrame | None, delivery_df: pd.DataFrame | None) -> list[ContractResult]:
    return [
        validate_required_columns(order_df, RAW_ORDER_REQUIRED, "주문 데이터"),
        validate_required_columns(delivery_df, RAW_DELIVERY_REQUIRED, "출고 데이터"),
    ]

