from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd


@dataclass(frozen=True)
class ContractIssue:
    severity: Literal["error", "warning"]
    code: str
    message: str


RAW_ORDER_REQUIRED = {"주문번호", "상품명"}
RAW_DELIVERY_REQUIRED = {"주문번호", "상품명", "배송예정일", "주문유형"}
ALLOWED_ORDER_TYPES = {"정상", "반품", "AS", "교환"}


def _required_issues(df: pd.DataFrame | None, required: set[str], name: str) -> list[ContractIssue]:
    if df is None:
        return [ContractIssue("error", f"{name}_missing_df", f"{name} 데이터프레임이 없습니다.")]
    cols = set(df.columns)
    missing = sorted(list(required - cols))
    if not missing:
        return []
    return [ContractIssue("error", f"{name}_missing_cols", f"{name} 필수 컬럼 누락: {', '.join(missing)}")]


def _nonnull_ratio_issue(df: pd.DataFrame, col: str, min_ratio: float, code: str, title: str) -> list[ContractIssue]:
    if col not in df.columns or df.empty:
        return []
    ratio = float(df[col].notna().mean())
    if ratio < min_ratio:
        return [ContractIssue("error", code, f"{title} 유효비율 {ratio:.2%} < 기준 {min_ratio:.2%}")]
    return []


def _datetime_parse_issue(
    df: pd.DataFrame, col: str, min_error: float, min_warn: float, code: str, title: str
) -> list[ContractIssue]:
    if col not in df.columns or df.empty:
        return []
    parsed = pd.to_datetime(df[col], errors="coerce")
    ratio = float(parsed.notna().mean())
    if ratio < min_error:
        return [ContractIssue("error", code, f"{title} 날짜 파싱 비율 {ratio:.2%} < 기준 {min_error:.2%}")]
    if ratio < min_warn:
        return [ContractIssue("warning", code, f"{title} 날짜 파싱 비율 저하 {ratio:.2%} (권장 {min_warn:.2%}+)")]
    return []


def _order_type_domain_issues(df: pd.DataFrame, col: str = "주문유형") -> list[ContractIssue]:
    if col not in df.columns or df.empty:
        return []
    s = df[col].astype(str).str.strip()
    unknown = ~s.isin(ALLOWED_ORDER_TYPES)
    ratio = float(unknown.mean())
    if ratio > 0.10:
        return [ContractIssue("error", "delivery_order_type_domain", f"주문유형 비허용 값 비율 {ratio:.2%} > 10%")]
    if ratio > 0.01:
        return [ContractIssue("warning", "delivery_order_type_domain", f"주문유형 비허용 값 비율 {ratio:.2%} > 1%")]
    return []


def validate_raw_inputs(order_df: pd.DataFrame | None, delivery_df: pd.DataFrame | None) -> tuple[list[ContractIssue], list[ContractIssue]]:
    issues: list[ContractIssue] = []
    issues.extend(_required_issues(order_df, RAW_ORDER_REQUIRED, "주문 데이터"))
    issues.extend(_required_issues(delivery_df, RAW_DELIVERY_REQUIRED, "출고 데이터"))

    if order_df is not None and not order_df.empty:
        issues.extend(_nonnull_ratio_issue(order_df, "주문번호", 0.995, "order_order_no_nonnull", "주문 데이터 주문번호"))
        issues.extend(_datetime_parse_issue(order_df, "등록일", 0.85, 0.95, "order_reg_dt_parse", "주문 데이터 등록일"))

    if delivery_df is not None and not delivery_df.empty:
        issues.extend(_nonnull_ratio_issue(delivery_df, "주문번호", 0.995, "delivery_order_no_nonnull", "출고 데이터 주문번호"))
        issues.extend(_datetime_parse_issue(delivery_df, "배송예정일", 0.90, 0.97, "delivery_scheduled_dt_parse", "출고 데이터 배송예정일"))
        issues.extend(_order_type_domain_issues(delivery_df, "주문유형"))

    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    return errors, warnings
