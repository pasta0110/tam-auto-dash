# data_loader.py
# 데이터 로드 및 전처리

import os
import streamlit as st
from config import (
    ORDER_CSV_PATH,
    DELIVERY_CSV_PATH,
    ORDER_CSV_URL,
    DELIVERY_CSV_URL,
    ERP_RUN_META_PATH,
    ERP_RUN_META_URL,
    UPLOADER_STATUS_PATH,
    UPLOADER_STATUS_URL,
)
from services.data_sources import RepositoryDataSource

try:
    from config import GITHUB_OWNER, GITHUB_REPO
except Exception:
    GITHUB_OWNER = "pasta0110"
    GITHUB_REPO = "tam-auto-dash"


class RawDataLoadError(RuntimeError):
    def __init__(self, message: str, diagnostics: dict):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


def _get_source() -> RepositoryDataSource:
    return RepositoryDataSource()

def _format_dt_kst(dt):
    try:
        from zoneinfo import ZoneInfo
        import datetime

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")
    except Exception:
        return str(dt)


def _http_last_modified(url: str):
    try:
        return _get_source().remote.head_meta(url)
    except Exception:
        return {"last_modified": None, "etag": None}


def _parse_github_iso_to_kst(iso: str):
    try:
        import datetime
        from zoneinfo import ZoneInfo

        # e.g. 2026-03-11T03:42:33Z
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")
    except Exception:
        return iso


@st.cache_data(ttl=300)
def get_github_last_commit_time(path: str):
    """
    Public GitHub API 기반: 특정 파일의 마지막 커밋 시각(KST) 반환.
    ERP 메타 파일이 없을 때(업로더 미실행) 최소한 'GitHub에 언제 올라갔는지'는 확인 가능.
    """
    try:
        iso = _get_source().remote.github_last_commit_time(GITHUB_OWNER, GITHUB_REPO, path)
        if not iso:
            return None
        return _parse_github_iso_to_kst(iso)
    except Exception:
        return None


@st.cache_data(ttl=300)
def get_erp_run_meta():
    """
    UI용: ERP 데이터 추출/업로드 시점을 표시하기 위한 메타 정보
    - 로컬 파일이 있으면 로컬 JSON
    - 아니면 GitHub raw JSON
    """
    try:
        source = _get_source()
        payload, _ = source.load_json_prefer_local(ERP_RUN_META_PATH, ERP_RUN_META_URL)
        return payload
    except Exception:
        return {}


@st.cache_data(ttl=120)
def get_uploader_status():
    """
    업로더 실행 결과 상태(성공/실패/코드/로그 경로)
    - 로컬 파일 우선
    - 없으면 GitHub raw JSON
    """
    try:
        source = _get_source()
        payload, _ = source.load_json_prefer_local(UPLOADER_STATUS_PATH, UPLOADER_STATUS_URL)
        return payload
    except Exception:
        return {}


@st.cache_data(ttl=300)
def get_data_snapshot_info():
    """
    UI용: 현재 앱이 보고 있는 CSV의 스냅샷 정보를 반환합니다.
    - 로컬 파일이 있으면 로컬 mtime
    - 아니면 GitHub raw의 Last-Modified 헤더(있으면)
    """
    info = {}

    source = _get_source()

    if os.path.exists(ORDER_CSV_PATH):
        info["order_source"] = "local"
        info["order_path_or_url"] = ORDER_CSV_PATH
        try:
            import datetime

            dt = datetime.datetime.fromtimestamp(source.local.mtime(ORDER_CSV_PATH))
            info["order_mtime_kst"] = _format_dt_kst(dt)
        except Exception:
            info["order_mtime_kst"] = None
    else:
        info["order_source"] = "remote"
        info["order_path_or_url"] = ORDER_CSV_URL
        meta = _http_last_modified(ORDER_CSV_URL)
        info["order_last_modified"] = meta["last_modified"]
        info["order_etag"] = meta["etag"]

    if os.path.exists(DELIVERY_CSV_PATH):
        info["delivery_source"] = "local"
        info["delivery_path_or_url"] = DELIVERY_CSV_PATH
        try:
            import datetime

            dt = datetime.datetime.fromtimestamp(source.local.mtime(DELIVERY_CSV_PATH))
            info["delivery_mtime_kst"] = _format_dt_kst(dt)
        except Exception:
            info["delivery_mtime_kst"] = None
    else:
        info["delivery_source"] = "remote"
        info["delivery_path_or_url"] = DELIVERY_CSV_URL
        meta = _http_last_modified(DELIVERY_CSV_URL)
        info["delivery_last_modified"] = meta["last_modified"]
        info["delivery_etag"] = meta["etag"]

    return info


@st.cache_data(ttl=300)
def load_raw_data():
    """
    하위 호환용: (order_df, delivery_df)만 반환
    상세 실패 원인은 load_raw_data_result() 사용
    """
    result = load_raw_data_result()
    ord_df, del_df = result["order_df"], result["delivery_df"]
    if ord_df is None or del_df is None:
        return None, None

    # 컬럼명 공백 제거
    ord_df.columns = [str(c).strip() for c in ord_df.columns]
    del_df.columns = [str(c).strip() for c in del_df.columns]
    return ord_df, del_df


@st.cache_data(ttl=300)
def load_raw_data_result():
    try:
        ord_df, del_df = load_raw_data_with_source(_get_source())
        ord_df.columns = [str(c).strip() for c in ord_df.columns]
        del_df.columns = [str(c).strip() for c in del_df.columns]
        return {
            "ok": True,
            "order_df": ord_df,
            "delivery_df": del_df,
            "error_message": "",
            "diagnostics": {},
        }
    except RawDataLoadError as e:
        return {
            "ok": False,
            "order_df": None,
            "delivery_df": None,
            "error_message": str(e),
            "diagnostics": e.diagnostics,
        }
    except Exception as e:
        return {
            "ok": False,
            "order_df": None,
            "delivery_df": None,
            "error_message": f"{type(e).__name__}: {e}",
            "diagnostics": {"unexpected_error": f"{type(e).__name__}: {e}"},
        }


def load_raw_data_with_source(source: RepositoryDataSource):
    ord_df, ord_diag = source.load_csv_with_diagnostics(ORDER_CSV_PATH, ORDER_CSV_URL)
    del_df, del_diag = source.load_csv_with_diagnostics(DELIVERY_CSV_PATH, DELIVERY_CSV_URL)
    if ord_df is None or del_df is None:
        diagnostics = {"order": ord_diag, "delivery": del_diag}
        failed_targets = []
        if ord_df is None:
            failed_targets.append("order.csv")
        if del_df is None:
            failed_targets.append("delivery.csv")
        target_text = ", ".join(failed_targets)
        message = f"{target_text} 로드 실패 (로컬→원격 순으로 시도)"
        raise RawDataLoadError(message, diagnostics)
    return ord_df, del_df
