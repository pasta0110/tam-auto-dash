# config.py
# 전역 설정 및 스타일

# 1. 데이터 소스
# 로컬(레포 내) ERP CSV가 있으면 우선 사용하고, 없을 때만 원격 URL을 사용합니다.
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ORDER_CSV_PATH = os.path.join(BASE_DIR, "order.csv")
DELIVERY_CSV_PATH = os.path.join(BASE_DIR, "delivery.csv")
ERP_RUN_META_PATH = os.path.join(BASE_DIR, "erp_run_meta.json")
UPLOADER_STATUS_PATH = os.path.join(BASE_DIR, "uploader_status.json")

GITHUB_OWNER = os.getenv("TDU_GITHUB_OWNER", "pasta0110")
GITHUB_REPO = os.getenv("TDU_GITHUB_REPO", "tam-auto-dash")
GITHUB_BRANCH = os.getenv("TDU_GITHUB_BRANCH", "main")

# 원격 CSV (레포에 csv가 포함되어 있으면 보통 필요 없지만, 배포 환경 대비용)
ORDER_CSV_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/raw/refs/heads/{GITHUB_BRANCH}/order.csv"
DELIVERY_CSV_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/raw/refs/heads/{GITHUB_BRANCH}/delivery.csv"
ERP_RUN_META_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/raw/refs/heads/{GITHUB_BRANCH}/erp_run_meta.json"
UPLOADER_STATUS_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/raw/refs/heads/{GITHUB_BRANCH}/uploader_status.json"

# 캐시 스키마 버전 (집계/파이프라인 로직 변경 시 버전 증가)
CACHE_SCHEMA_VERSION = "2026.03.17.v2"

# 2. 지역별 센터 순서 (정렬 기준)
V_ORDER = ["수도권", "대전", "대구", "부산", "경남", "광주", "전주", "강원"]

# 3. CSS 스타일 정의 (표 및 화면)
APP_TITLE = "청호나이스 현황판"
APP_ICON = "📊"

CSS_STYLE = """
<style>
/* 전체 표 공통 설정 */
th, td {
    text-align: center !important;
    vertical-align: middle !important;
}
.stTable td {
    text-align: center !important;
}
/* 헤더 스타일 */
thead tr th {
    background-color: #f0f2f6 !important;
    color: #31333F !important;
}
/* 🌟 [강력 강조] 메인 '합계' 또는 '총계' 행 */
tr:has(th:contains("합계")), tr:has(td:contains("합계")), tr:has(th:contains("총계")), tr:has(td:contains("총계")) {
    background-color: #3d3d3d !important;
    font-weight: bold !important;
}
/* 글자색 흰색 고정 */
tr:has(th:contains("합계")) th, tr:has(td:contains("합계")) td, tr:has(th:contains("총계")) th, tr:has(td:contains("총계")) td {
    color: #FFFFFF !important;
}
/* 🌟 [은은한 강조] '판넬' 단어가 포함된 합계 행 */
tr:has(th:contains("판넬")), tr:has(td:contains("판넬")) {
    background-color: #e9ecef !important;
    font-weight: bold !important;
}
/* 글자색 검은색 고정 */
tr:has(th:contains("판넬")) th, tr:has(td:contains("판넬")) td {
    color: #31333F !important;
}
/* 모바일 기기 보정 */
@media (max-width: 640px) {
    .stTable {
        font-size: 12px !important;
    }
}
/* 상단 탭 글자 크기 조정 */
button[data-baseweb="tab"] {
    font-size: 16px !important;
    font-weight: bold;
}
</style>
"""
