import os
import sys
import json
import subprocess
import shutil
import traceback
import requests
import pandas as pd
from io import BytesIO
import calendar
from datetime import datetime


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

# ==========================================
# 1. 기본 설정
# ==========================================

git_repo_path = r"C:\Users\alcls\Documents\tam-auto-dash"
run_meta_path = os.path.join(git_repo_path, "erp_run_meta.json")

session = requests.Session()

today = datetime.today()
start_date = "2025-02-01"

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

# ==========================================
# 2. ERP CSV 다운로드
# ==========================================

def _get_erp_credentials():
    login_id = os.getenv("ERP_LOGIN_ID")
    login_pw = os.getenv("ERP_LOGIN_PW")
    if not login_id or not login_pw:
        raise RuntimeError(
            "ERP 로그인 환경변수(ERP_LOGIN_ID, ERP_LOGIN_PW)가 설정되지 않았습니다.\n"
            "- PowerShell(현재 세션): $env:ERP_LOGIN_ID='아이디'; $env:ERP_LOGIN_PW='비밀번호'\n"
            "- 영구 설정(새 터미널에서 적용): setx ERP_LOGIN_ID \"아이디\"; setx ERP_LOGIN_PW \"비밀번호\""
        )
    return login_id, login_pw


def download_erp_csv():

    print("\n🚀 ERP CSV 다운로드 시작...")

    login_id, login_pw = _get_erp_credentials()

    # 로그인
    login_data = {"login_id": login_id, "login_passwd": login_pw}

    resp = session.post("http://ene.kins.co.kr/loginCheck.do", data=login_data)
    resp.raise_for_status()

    try:
        login_json = resp.json()
    except Exception as e:
        raise RuntimeError("ERP 로그인 응답이 JSON 형식이 아닙니다.") from e

    if login_json.get("result") != "success":
        raise RuntimeError(f"ERP 로그인 실패: {login_json}")

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

    print("📦 출고 데이터 다운로드 중...")

    resp = session.post(dl_url, data=delivery_p)
    resp.raise_for_status()
    delivery_df = pd.read_excel(BytesIO(resp.content))
    delivery_path = os.path.join(git_repo_path, "delivery.csv")
    delivery_df.to_csv(delivery_path, index=False, encoding="utf-8-sig")
    print("✅ delivery.csv 생성 완료")

    # =========================
    # 주문 데이터 다운로드
    # =========================

    print("📦 주문 데이터 다운로드 중...")

    resp = session.post(dl_url, data=order_p)
    resp.raise_for_status()
    order_df = pd.read_excel(BytesIO(resp.content))
    order_path = os.path.join(git_repo_path, "order.csv")
    order_df.to_csv(order_path, index=False, encoding="utf-8-sig")
    print("✅ order.csv 생성 완료")

    return {"order_rows": int(order_df.shape[0]), "delivery_rows": int(delivery_df.shape[0])}


# ==========================================
# 3. GitHub 업로드
# ==========================================

def upload_to_github():

    print(f"\n✨ [작업 시작] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:

        # ERP 데이터 먼저 다운로드
        extracted_at = _now_kst()
        meta = {"extracted_at_kst": extracted_at.strftime("%Y-%m-%d %H:%M:%S KST")}
        meta.update(download_erp_csv() or {})

        # 작업 디렉토리 이동
        if not os.path.exists(git_repo_path):
            print(f"❌ 폴더를 찾을 수 없습니다: {git_repo_path}")
            return

        os.chdir(git_repo_path)

        # 필수 파일 확인
        required_files = ["app.py", "requirements.txt"]

        missing_files = [f for f in required_files if not os.path.exists(f)]

        if missing_files:
            print(f"⚠️ 경고: 다음 파일이 누락되었습니다: {missing_files}")

        # ==========================
        # Git 동기화
        # ==========================

        print("🔄 원격 저장소와 상태를 맞추는 중...")

        subprocess.run(
            ["git", "fetch", "origin", "main"],
            capture_output=True
        )

        subprocess.run(
            ["git", "pull", "origin", "main", "--rebase"],
            capture_output=True
        )

        # ==========================
        # 변경사항 추가
        # ==========================

        print("📦 변경사항 패키징 중 (add .)...")

        subprocess.run(
            ["git", "add", "."],
            check=True
        )

        # 변경 여부 확인

        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            text=True
        )

        if not status:
            print("ℹ️ 업데이트할 내용이 없습니다. 작업 종료.")
            return

        # ==========================
        # 커밋
        # ==========================

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

        commit_msg = f"📦 ERP 데이터 자동 업데이트 ({now_str})"

        # 메타 파일 기록(커밋에 포함되게 커밋 직전에 저장)
        commit_at = _now_kst()
        meta["commit_at_kst"] = commit_at.strftime("%Y-%m-%d %H:%M:%S KST")
        _write_run_meta(run_meta_path, meta)

        subprocess.run(
            ["git", "commit", "-m", commit_msg],
            capture_output=True
        )

        # ==========================
        # 푸시
        # ==========================

        print("🚀 깃허브로 전송 중...")

        result = subprocess.run(
            ["git", "push", "origin", "main"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:

            print(f"✅ 최종 성공! [메시지: {commit_msg}]")

        else:

            print("⚠️ 일반 전송 실패, 강제 전송 시도...")

            subprocess.run(
                ["git", "push", "origin", "main", "--force"],
                check=True
            )

            print("🔥 강제 전송 완료!")

    except Exception:
        print("❌ 오류 발생! (작업 중단)")
        traceback.print_exc()
        raise SystemExit(1)


# ==========================================
# 4. 실행
# ==========================================

if __name__ == "__main__":
    upload_to_github()
