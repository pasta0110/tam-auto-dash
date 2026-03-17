# tam-auto-dash

청호나이스 출고/주문 데이터를 기반으로 운영 지표를 시각화하는 Streamlit 대시보드입니다.

## 1) 구성
- 앱 진입점: `app.py`
- 탭 화면: `tabs/`
- 공통 서비스: `services/`
- 데이터 로딩/전처리: `data_loader.py`, `data_processor.py`
- 업로더(표준): `ch_NEW_smart_uploader.py`

## 2) 현재 데이터 파이프라인
- 원천 파일: `order.csv`, `delivery.csv`
- 메타: `erp_run_meta.json`
- 업로더 상태: `uploader_status.json`
- 무결성 기준: `order/delivery` 해시와 `erp_run_meta.json`의 해시 일치 여부

## 3) 실행 방법
```bash
streamlit run app.py
```

## 4) 업로더 실행
### 사전 환경변수
- `ERP_LOGIN_ID`
- `ERP_LOGIN_PW`
- (선택) `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

### 기본 실행
```bash
python ch_NEW_smart_uploader.py
```

### 점검 모드
```bash
python ch_NEW_smart_uploader.py --health-check
python ch_NEW_smart_uploader.py --dry-run
python ch_NEW_smart_uploader.py --simulate-fail-step git
```

## 5) 배치 역할 분리 (중요)
- `주문출고.bat`: 엑셀 관리 자동화 전용 (업로드 기능 없음)
- `깃허브_업로드.bat`: ERP CSV 추출 + GitHub 업로드 전용

## 6) 운영 체크 포인트
- 앱 상단 `데이터 기준` 시각이 최신인지 확인
- `무결성: ✅ meta-hash 일치` 확인
- 필요 시 `?ops=1`로 Ops Panel 확인
- GitHub Actions `Guardrails` 성공 여부 확인

## 7) 참고 문서
- 운영 런북: `docs/OPERATIONS_RUNBOOK.md`
