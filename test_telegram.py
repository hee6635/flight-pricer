import os
import requests

def test_telegram():
    # 1. 환경 변수에서 토큰과 챗ID 가져오기
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("CHAT_ID")

    print("========================================")
    print("🔍 텔레그램 전송 테스트 시작")
    print("========================================")
    
    # 2. 값이 제대로 들어왔는지 체크 (토큰은 보안상 앞 5자리만 확인)
    token_status = f"성공 (앞자리: {token[:5]}...)" if token else "실패 (값이 비어있음!)"
    chat_id_status = f"성공 ({chat_id})" if chat_id else "실패 (값이 비어있음!)"
    
    print(f"▶️ TELEGRAM_TOKEN 로드: {token_status}")
    print(f"▶️ CHAT_ID 로드: {chat_id_status}")

    if not token or not chat_id:
        print("🚨 오류: GitHub Secrets에 값이 제대로 설정되지 않았습니다.")
        return

    # 3. 텔레그램 서버로 요청 보내기
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": "🚀 GitHub Actions에서 보내는 텔레그램 테스트 메시지입니다!\n이 메시지가 보인다면 연결이 완벽하게 된 것입니다.",
        "parse_mode": "Markdown"
    }

    print("\n📡 텔레그램 서버로 전송 시도 중...")
    try:
        response = requests.post(url, data=payload)
        print(f"📥 텔레그램 서버 응답 코드: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ 전송 성공! 스마트폰 텔레그램 앱을 확인해보세요.")
        else:
            print(f"❌ 전송 실패! 상세 에러 원인:\n{response.text}")
    except Exception as e:
        print(f"💥 치명적 에러 발생: {e}")

if __name__ == "__main__":
    test_telegram()

