import os
import sys
import json
import argparse
import subprocess
import traceback
import requests
import pandas as pd
from io import BytesIO
import calendar
from datetime import datetime
from services.integrity import file_sha256


# Windows 기본 콘솔(cp949 등)에서 이모지 출력 시 UnicodeEncodeError가 날 수 있어 UTF-8로 고정
def _configure_utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


_configure_utf8_stdio()

def _now_kst():
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Seoul"))
    except Exception:
        return datetime.now()


def _write_run_meta(path: str, meta: dict):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _write_uploader_status(ok: bool, code: int, message: str, extra: dict | None = None):
    payload = {
        "ok": bool(ok),
        "exit_code": int(code),
        "message": str(message),
        "updated_at_kst": _now_kst().strftime("%Y-%m-%d %H:%M:%S KST"),
        "log_file": os.getenv("UPLOADER_LOG_FILE", ""),
    }
    if extra:
        payload.update(extra)
    try:
        with open(uploader_status_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _run(cmd: list[str], cwd: str | None = None, check: bool = True):
    """
    subprocess 실행 래퍼:
    - 실패 시 stdout/stderr를 즉시 출력해 원인 은폐를 막음
    """
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and result.returncode != 0:
        print(f"[ERROR] Command failed: {' '.join(cmd)}")
        if result.stdout:
            print("[stdout]")
            print(result.stdout.strip())
        if result.stderr:
            print("[stderr]")
            print(result.stderr.strip())
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(cmd)}")
    return result

# ==========================================
# 1. 기본 설정
# ==========================================

git_repo_path = r"C:\Users\alcls\Documents\tam-auto-dash"
run_meta_path = os.path.join(git_repo_path, "erp_run_meta.json")
uploader_status_path = os.path.join(git_repo_path, "uploader_status.json")

session = requests.Session()

today = datetime.today()
start_date = "2025-02-01"
ORDER_TARGET_MAX_ROWS = 40000
ORDER_MAX_LOOKBACK_MONTHS = 24
EXIT_OK = 0
EXIT_ENV = 10
EXIT_REPO = 11
EXIT_GIT_SYNC = 12
EXIT_ERP = 13
EXIT_COMMIT = 15
EXIT_PUSH = 16
EXIT_UNKNOWN = 1

def _shift_month(year: int, month: int, delta_months: int):
    m = month + delta_months
    y = year + (m - 1) // 12
    m = ((m - 1) % 12) + 1
    return y, m


def _month_range_ym(year: int, month: int):
    first = datetime(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    last = datetime(year, month, last_day)
    return first, last


# 출고(배송) 조회 기간: 기존 유지 (고정 시작 ~ 당월 기준 +3개월 말일)
future_year, future_month = _shift_month(today.year, today.month, 3)
_, future_last = _month_range_ym(future_year, future_month)
end_date = future_last.strftime("%Y-%m-%d")

# 주문 조회 기간: 당월 기준 -6개월 1일 ~ +3개월 말일
order_start_y, order_start_m = _shift_month(today.year, today.month, -6)
order_end_y, order_end_m = _shift_month(today.year, today.month, 3)
order_start, _ = _month_range_ym(order_start_y, order_start_m)
_, order_end = _month_range_ym(order_end_y, order_end_m)
order_start_date = order_start.strftime("%Y-%m-%d")
order_end_date = order_end.strftime("%Y-%m-%d")


def _iter_months_desc(start_year: int, start_month: int, n_months: int):
    y, m = start_year, start_month
    for _ in range(n_months):
        yield y, m
        y, m = _shift_month(y, m, -1)


def _download_excel_df(dl_url: str, params: dict) -> pd.DataFrame:
    resp = session.post(dl_url, data=params)
    resp.raise_for_status()
    return pd.read_excel(BytesIO(resp.content))


# ==========================================
# 2. ERP CSV 다운로드
# ==========================================

def _get_erp_credentials():
    login_id = os.getenv("ERP_LOGIN_ID")
    login_pw = os.getenv("ERP_LOGIN_PW")
    if not login_id or not login_pw:
        raise RuntimeError(
            "Missing ERP credentials in environment variables (ERP_LOGIN_ID, ERP_LOGIN_PW).\n"
            "- PowerShell (current session): $env:ERP_LOGIN_ID='YOUR_ID'; $env:ERP_LOGIN_PW='YOUR_PW'\n"
            "- Persistent: setx ERP_LOGIN_ID \"YOUR_ID\"; setx ERP_LOGIN_PW \"YOUR_PW\""
        )
    return login_id, login_pw


def download_erp_csv():

    print("\n[START] ERP CSV download")

    login_id, login_pw = _get_erp_credentials()

    # 로그인
    login_data = {"login_id": login_id, "login_passwd": login_pw}

    resp = session.post("http://ene.kins.co.kr/loginCheck.do", data=login_data)
    resp.raise_for_status()

    try:
        login_json = resp.json()
    except Exception as e:
        raise RuntimeError("ERP login response is not valid JSON.") from e

    if login_json.get("result") != "success":
        raise RuntimeError(f"ERP login failed: {login_json}")

    session.post(
        "http://ene.kins.co.kr/loginAction.do",
        data={"user_id": login_id, "isMobile": "false"},
    ).raise_for_status()

    dl_url = "http://ene.kins.co.kr/excel/downloadExcel.do"

    # =========================
    # 출고 파라미터
    # =========================

    delivery_p = {
        "delivery_dt_from": start_date,
        "delivery_dt_to": end_date,
        "url": "/delivery/deliveryList.do",
        "id": "delivery_list",
        "rows": "5000",
        "page": "1",
        "sord": "asc",
        "_search": "false",
        "colNames[]": [
            "매출처",
            "주문유형",
            "주문상태",
            "배송유형",
            "배송상태",
            "주문등록일",
            "해피콜",
            "해피콜시간",
            "배송예정일",
            "배송예정시간",
            "도착시간",
            "완료시간",
            "배송사",
            "배송담당",
            "상담메시지",
            "배송완료메모",
            "주문번호",
            "상품명",
            "수취인",
            "주소",
            "휴대전화",
            "전화",
            "판매인메모",
            "주문확정메모",
            "배송자메모",
            "상품코드",
            "수량",
            "옵션",
            "우편번호",
            "배송담당자 전화",
            "바코드번호",
            "제조일자",
            "검사자",
            "배송기사ID",
            "수정",
        ],
        "dbColNames[]": [
            "sales_comp_nm",
            "order_type_nm",
            "order_stat_nm",
            "delivery_order_nm",
            "delivery_stat_nm",
            "order_reg_dt",
            "happy_call",
            "happy_call_dt",
            "delivery_dt",
            "delivery_dt_time",
            "arrived_time",
            "complete_dt",
            "delivery_comp_nm",
            "delivery_user_nm",
            "send_msg",
            "delivery_complete_msg",
            "order_no",
            "product_nm",
            "customer_nm",
            "customer_order_address",
            "customer_hp",
            "customer_phone",
            "delivery_msg",
            "ins_send_msg",
            "delivery_memo",
            "product_cd",
            "cnt",
            "order_option",
            "post_no",
            "delivery_user_hp",
            "barcode_no",
            "manufacturing_date",
            "inspector",
            "delivery_user_id",
            "",
        ],
    }

    # =========================
    # 주문 파라미터
    # =========================

    order_p = {
        "order_date_from": order_start_date,
        "order_date_to": order_end_date,
        "url": "/order/orderList.do",
        "id": "order_list",
        "non_target": "0",
        "rows": "5000",
        "page": "1",
        "sord": "asc",
        "_search": "false",
        "colNames[]": [
            "매출처",
            "주문유형",
            "배송유형",
            "주문번호",
            "주문상태",
            "해피콜",
            "상품코드",
            "상품명",
            "판매인메모",
            "수취인",
            "수취인연락처",
            "상담메시지",
            "등록일",
            "배송예정일",
            "담당자",
            "배송사",
            "판매인",
            "판매인연락처",
            "우편번호",
            "주소",
            "판매지국",
            "판매지국 연락처",
            "문서번호",
            "제품구분",
            "접수유형",
            "판정",
            "조치결과",
            "수정",
        ],
        "dbColNames[]": [
            "comp_nm",
            "order_type_nm",
            "delivery_order_type_nm",
            "order_no",
            "order_stat_nm",
            "happy_call",
            "product_cd",
            "product_nm",
            "delivery_msg",
            "customer_nm",
            "customer_hp",
            "send_msg",
            "reg_dt",
            "delivery_schedule_dt",
            "happycall_user_nm",
            "delivery_comp_nm",
            "order_nm",
            "order_hp",
            "post_no",
            "customer_order_address",
            "sale_branch",
            "sale_branch_phone",
            "doc_no",
            "classCd",
            "rcptType",
            "asStat",
            "asResult",
            "",
        ],
    }

    # =========================
    # 출고 데이터 다운로드
    # =========================

    print("[STEP] Downloading delivery data...")

    resp = session.post(dl_url, data=delivery_p)
    resp.raise_for_status()
    delivery_df = pd.read_excel(BytesIO(resp.content))
    delivery_path = os.path.join(git_repo_path, "delivery.csv")
    delivery_df.to_csv(delivery_path, index=False, encoding="utf-8-sig")
    print("[OK] delivery.csv generated")

    # =========================
    # 주문 데이터 다운로드
    # =========================

    print("[STEP] Downloading order data... (monthly full-window, near 40k validation)")

    month_frames = []
    included = []
    cum_rows = 0
    last_from = None
    last_to = None

    for y, m in _iter_months_desc(order_end_y, order_end_m, ORDER_MAX_LOOKBACK_MONTHS):
        m_first, m_last = _month_range_ym(y, m)
        m_from = m_first.strftime("%Y-%m-%d")
        m_to = m_last.strftime("%Y-%m-%d")

        month_p = dict(order_p)
        month_p["order_date_from"] = m_from
        month_p["order_date_to"] = m_to

        df_m = _download_excel_df(dl_url, month_p)
        rows_m = int(df_m.shape[0])
        ym = f"{y:04d}-{m:02d}"
        print(f"  - {ym}: {rows_m:,} rows")

        if rows_m == 0:
            continue

        if month_frames and (cum_rows + rows_m > ORDER_TARGET_MAX_ROWS):
            print(f"  -> stop at cumulative {cum_rows:,} rows (next month would be {cum_rows + rows_m:,})")
            break

        month_frames.append(df_m)
        included.append(ym)
        cum_rows += rows_m
        last_from = m_from
        last_to = m_to

    if month_frames:
        order_df = pd.concat(month_frames, ignore_index=True)
        print(
            "[OK] Order month-window selected: "
            f"{included[-1]}~{included[0]} (months={len(included)}, cumulative={cum_rows:,}/{ORDER_TARGET_MAX_ROWS:,})"
        )
    else:
        # 월별 조회 실패/데이터 없음 시 기존 단일 기간 조회로 fallback
        print("[WARN] Monthly query returned no data. Fallback to default date-range query.")
        fallback_p = dict(order_p)
        fallback_p["order_date_from"] = order_start_date
        fallback_p["order_date_to"] = order_end_date
        order_df = _download_excel_df(dl_url, fallback_p)
        last_from = order_start_date
        last_to = order_end_date

    order_path = os.path.join(git_repo_path, "order.csv")
    order_df.to_csv(order_path, index=False, encoding="utf-8-sig")
    print("[OK] order.csv generated")

    order_sha256 = file_sha256(order_path)
    delivery_sha256 = file_sha256(delivery_path)

    return {
        "order_rows": int(order_df.shape[0]),
        "delivery_rows": int(delivery_df.shape[0]),
        "order_sha256": order_sha256,
        "delivery_sha256": delivery_sha256,
        "order_target_max_rows": ORDER_TARGET_MAX_ROWS,
        "order_selected_months": len(included),
        "order_window_from": last_from,
        "order_window_to": last_to,
    }


# ==========================================
# 3. GitHub 업로드
# ==========================================

def health_check() -> tuple[int, str]:
    try:
        _get_erp_credentials()
    except Exception as e:
        return EXIT_ENV, f"ERP credential check failed: {e}"
    if not os.path.exists(git_repo_path):
        return EXIT_REPO, f"Repo path not found: {git_repo_path}"
    try:
        _run(["git", "--version"], cwd=git_repo_path, check=True)
        _run(["git", "remote", "-v"], cwd=git_repo_path, check=True)
    except Exception as e:
        return EXIT_GIT_SYNC, f"Git check failed: {e}"
    return EXIT_OK, "Health check passed"


def upload_to_github(dry_run: bool = False) -> int:
    print(f"\n[JOB START] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        if not os.path.exists(git_repo_path):
            print(f"[ERROR] Repo path not found: {git_repo_path}")
            _write_uploader_status(False, EXIT_REPO, "Repo path not found")
            return EXIT_REPO

        os.chdir(git_repo_path)

        required_files = ["app.py", "requirements.txt"]
        missing_files = [f for f in required_files if not os.path.exists(f)]
        if missing_files:
            print(f"[WARN] Missing required files: {missing_files}")

        print("[STEP] Syncing with remote repository...")
        try:
            _run(["git", "fetch", "origin", "main"], cwd=git_repo_path, check=True)
            _run(["git", "pull", "--rebase", "--autostash", "origin", "main"], cwd=git_repo_path, check=True)
        except Exception as e:
            _write_uploader_status(False, EXIT_GIT_SYNC, f"Git sync failed: {e}")
            return EXIT_GIT_SYNC

        extracted_at = _now_kst()
        meta = {"extracted_at_kst": extracted_at.strftime("%Y-%m-%d %H:%M:%S KST")}
        try:
            meta.update(download_erp_csv() or {})
        except Exception as e:
            print("[ERROR] ERP download failed.")
            traceback.print_exc()
            _write_uploader_status(False, EXIT_ERP, f"ERP download failed: {e}")
            return EXIT_ERP

        commit_at = _now_kst()
        meta["commit_at_kst"] = commit_at.strftime("%Y-%m-%d %H:%M:%S KST")
        _write_run_meta(run_meta_path, meta)
        _write_uploader_status(True, EXIT_OK, "Prepared upload (before commit)", extra={"phase": "pre_commit"})

        print("[STEP] Staging changed files (order/delivery/meta/status)...")
        tracked_files = ["order.csv", "delivery.csv", "erp_run_meta.json", "uploader_status.json"]
        _run(["git", "add"] + tracked_files, cwd=git_repo_path, check=True)

        staged = _run(["git", "diff", "--cached", "--name-only"], cwd=git_repo_path, check=True).stdout.strip()
        if not staged:
            print("[INFO] No changes to commit. Job done.")
            _write_uploader_status(True, EXIT_OK, "No changes to commit")
            return EXIT_OK

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
        commit_msg = f"ERP auto update ({now_str})"
        try:
            _run(["git", "commit", "-m", commit_msg], cwd=git_repo_path, check=True)
        except Exception as e:
            _write_uploader_status(False, EXIT_COMMIT, f"Commit failed: {e}")
            return EXIT_COMMIT

        changed = _run(["git", "show", "--name-only", "--pretty=format:", "HEAD"], cwd=git_repo_path, check=True).stdout
        changed_set = set([x.strip() for x in changed.splitlines() if x.strip()])
        required_changed = {"order.csv", "delivery.csv", "erp_run_meta.json"}
        if not required_changed.issubset(changed_set):
            msg = f"Commit verification failed. changed={sorted(changed_set)}"
            print(f"[ERROR] {msg}")
            _write_uploader_status(False, EXIT_COMMIT, msg)
            return EXIT_COMMIT

        if dry_run:
            print("[DRY-RUN] Commit created; push skipped.")
            _write_uploader_status(True, EXIT_OK, "Dry-run completed (commit only, no push)")
            return EXIT_OK

        print("[STEP] Pushing to GitHub...")
        try:
            _run(["git", "push", "origin", "main"], cwd=git_repo_path, check=True)
        except Exception as e:
            _write_uploader_status(False, EXIT_PUSH, f"Push failed: {e}")
            return EXIT_PUSH

        print(f"[SUCCESS] Completed: {commit_msg}")
        _write_uploader_status(True, EXIT_OK, "Upload completed", extra={"commit_message": commit_msg})
        return EXIT_OK

    except Exception:
        print("[ERROR] Job failed.")
        traceback.print_exc()
        _write_uploader_status(False, EXIT_UNKNOWN, "Unhandled exception")
        return EXIT_UNKNOWN


# ==========================================
# 4. 실행
# ==========================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--health-check", action="store_true", help="Validate env/repo/git only and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Run full flow but skip push.")
    args = parser.parse_args()

    if args.health_check:
        code, msg = health_check()
        print(f"[HEALTH] code={code} msg={msg}")
        _write_uploader_status(code == EXIT_OK, code, msg)
        sys.exit(code)

    rc = upload_to_github(dry_run=args.dry_run)
    sys.exit(rc)
