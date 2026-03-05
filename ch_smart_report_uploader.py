import os
import subprocess
import datetime
import shutil
import traceback

# 1. 경로 설정 (탬버쌤의 실제 경로)
git_repo_path = r"C:\Users\alcls\Documents\tam-auto-dash"
# 원본 데이터 파일이 있는 경로 (예시: WSL 또는 바탕화면 등)
# 만약 이미 git_repo_path 안에 파일들이 있다면 이 복사 과정은 생략 가능합니다.
source_data_path = r"C:\원본데이터_경로\data.xlsx" 

def upload_to_github():
    print(f"\n✨ [작업 시작] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # 1. 작업 디렉토리 이동
        if not os.path.exists(git_repo_path):
            print(f"❌ 폴더를 찾을 수 없습니다: {git_repo_path}")
            return
        os.chdir(git_repo_path)

        # 2. 최신 파일 복사 (필요한 경우만 실행)
        # 만약 스크립트 외부에서 파일을 이미 옮겨두셨다면 이 줄은 주석 처리하세요.
        # shutil.copy2(source_data_path, os.path.join(git_repo_path, "data.xlsx"))

        # 3. 필수 파일 존재 여부 확인 (안전 장치)
        required_files = ["data.xlsx", "app.py", "requirements.txt"]
        missing_files = [f for f in required_files if not os.path.exists(f)]
        if missing_files:
            print(f"⚠️ 경고: 다음 파일이 누락되었습니다: {missing_files}")
            # 누락되어도 계속 진행하려면 여기서 중단하지 않습니다.

        # 4. Git 동기화 로직 (핵심)
        print("🔄 원격 저장소와 상태를 맞추는 중...")
        subprocess.run(["git", "fetch", "origin", "main"], capture_output=True)
        # 로컬의 변경사항을 유지하면서 원격의 변화를 가져옴 (rebase)
        subprocess.run(["git", "pull", "origin", "main", "--rebase"], capture_output=True)

        # 5. 모든 변경사항 담기 (git add .)
        # 탬버쌤이 말씀하신 3가지 파일 및 수정사항을 모두 박스에 담습니다.
        print("📦 변경사항 패키징 중 (add .)...")
        subprocess.run(["git", "add", "."], check=True)

        # 6. 변경사항 확인 (변화가 없으면 푸시 안 함)
        status = subprocess.check_output(["git", "status", "--porcelain"], text=True)
        if not status:
            print("ℹ️ 업데이트할 내용이 없습니다. 작업을 종료합니다.")
            return

        # 7. 커밋 (이름표 붙이기)
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        commit_msg = f"🚀 실시간 업데이트 ({now_str})"
        subprocess.run(["git", "commit", "-m", commit_msg], capture_output=True)

        # 8. 푸시 (트럭 발송)
        print("🚀 깃허브로 전송 중... (잠시만 기다려주세요)")
        # 탬버쌤, 여기서 시간이 조금 걸릴 수 있지만 정상입니다 (약 6.5MB 전송)
        result = subprocess.run(["git", "push", "origin", "main"], capture_output=True, text=True)

        if result.returncode == 0:
            print(f"✅ 최종 성공! [메시지: {commit_msg}]")
        else:
            print("⚠️ 일반 전송 실패, 강제 전송 시도...")
            subprocess.run(["git", "push", "origin", "main", "--force"], check=True)
            print("🔥 강제 전송으로 해결했습니다!")

    except Exception as e:
        print(f"❌ 오류 발생!")
        traceback.print_exc()

# 테스트 실행
if __name__ == "__main__":
    upload_to_github()