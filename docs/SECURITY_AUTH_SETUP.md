# 보안 로그인 설정 (카카오 + 화이트리스트 + PIN + 텔레그램)

이 기능은 기본 OFF 상태이며, `AUTH_ENABLED=true`를 넣었을 때만 동작합니다.

## 1) Streamlit Secrets 예시
아래를 Streamlit Cloud `Settings > Secrets`에 추가하세요.

```toml
AUTH_ENABLED = true

AUTH_KAKAO_CLIENT_ID = "카카오 REST API KEY"
AUTH_KAKAO_CLIENT_SECRET = "선택(있으면 입력)"
AUTH_KAKAO_REDIRECT_URI = "https://<your-app>.streamlit.app"

# 화이트리스트: 둘 중 하나라도 매칭되면 통과
AUTH_KAKAO_WHITELIST_IDS = ["1234567890", "2345678901"]
AUTH_KAKAO_WHITELIST_EMAILS = ["ceo@company.com", "ops@company.com"]

# 관리자 지정(선택): 없으면 전원 일반
AUTH_ADMIN_KAKAO_IDS = ["1234567890"]

# PIN: 권한별 (평문 또는 SHA256 중 1개)
AUTH_PIN_USER_CODE = "351037"
AUTH_PIN_ADMIN_CODE = "144883"
# AUTH_PIN_USER_SHA256 = "..."
# AUTH_PIN_ADMIN_SHA256 = "..."

AUTH_PIN_MAX_ATTEMPTS = 5
AUTH_SESSION_MINUTES = 10

TELEGRAM_BOT_TOKEN = "bot token"
TELEGRAM_CHAT_ID = "chat id"
```

## 2) 카카오 개발자 콘솔 설정
- 플랫폼: Web
- Redirect URI: `AUTH_KAKAO_REDIRECT_URI` 값과 동일하게 등록
- 동의항목: `닉네임` 사용 (`이메일`은 권한이 있을 때만)

## 3) 동작 순서
1. 카카오 OAuth 로그인
2. 화이트리스트 체크(ID 또는 이메일)
3. 권한별 PIN 2차 인증(일반/관리자)
4. 텔레그램 인증 로그 발송

## 4) 운영 권장
- 최초 적용은 내부 테스트 계정 1~2개로 확인
- PIN은 평문 대신 `AUTH_PIN_SHA256` 사용 권장
- 텔레그램 알림이 오지 않으면 토큰/챗ID 먼저 점검
