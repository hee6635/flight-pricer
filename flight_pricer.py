import os
import click
import requests
import random
import json
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

def send_telegram(message):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("CHAT_ID")
    if not token or not chat_id: return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": True})

def get_serpapi_key():
    """등록된 키 로테이션 및 현재 사용 중인 키 번호 반환"""
    keys = [(i, os.getenv(f"SERPAPI_KEY_{i}")) for i in range(1, 9)]
    valid_keys = [(i, k) for i, k in keys if k]
    if not valid_keys: return None, None
    idx, key = random.choice(valid_keys)
    return idx, key

def update_gsheet(data_row):
    """구글 시트에 데이터를 실시간으로 기록합니다."""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        # GitHub Secrets에서 JSON 키 로드
        creds_json_str = os.getenv("GSPREAD_SERVICE_ACCOUNT")
        if not creds_json_str:
            print("⚠️ 구글 시트 인증 정보가 없습니다 (GSPREAD_SERVICE_ACCOUNT Secret 확인)")
            return
        
        creds_json = json.loads(creds_json_str)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        
        # '방콕항공권' 시트의 첫 번째 워크시트에 데이터 추가
        sheet = client.open("방콕항공권").sheet1
        sheet.append_row(data_row)
        print("📊 구글 시트 데이터 기록 성공!")
    except Exception as e:
        print(f"❌ 구글 시트 기록 실패: {e}")

def fetch_oneway(api_key, from_iata, to_iata, date_str):
    params = {
        "engine": "google_flights",
        "departure_id": from_iata,
        "arrival_id": to_iata,
        "outbound_date": date_str,
        "type": 2, # 편도
        "adults": 2, 
        "currency": "KRW",
        "hl": "ko",
        "api_key": api_key
    }
    try:
        data = requests.get("https://serpapi.com/search", params=params).json()
        return data.get("best_flights", []) + data.get("other_flights", [])
    except:
        return []

def parse_flights(flight_data, expected_from, expected_to):
    parsed = []
    for item in flight_data:
        price = item.get("price", 0)
        flights = item.get("flights", [])
        
        # 직항(길이 1)만 허용
        if not flights or price == 0 or len(flights) != 1: continue 
        
        f = flights[0]
        # 출발지 정확도 검증
        if f.get("departure_airport", {}).get("id") != expected_from: continue
            
        dep_dt = datetime.strptime(f.get("departure_airport", {}).get("time"), "%Y-%m-%d %H:%M")
        arr_dt = datetime.strptime(f.get("arrival_airport", {}).get("time"), "%Y-%m-%d %H:%M")
        
        # 소요 시간 및 +1일 여부 계산
        duration = arr_dt - dep_dt
        hours, remainder = divmod(duration.seconds, 3600)
        minutes = remainder // 60
        is_next_day = "+1일" if arr_dt.date() > dep_dt.date() else ""

        parsed.append({
            "airline": f.get("airline", "Unknown"),
            "time_info": f"{dep_dt.strftime('%H:%M')} ~ {arr_dt.strftime('%H:%M')} {is_next_day}",
            "duration": f"{hours}시간 {minutes}분",
            "price_total": price,
            "price_per": price // 2
        })
    return sorted(parsed, key=lambda x: x["price_total"])[:3]

@click.group()
def cli(): pass

@cli.command()
@click.option('--from', 'from_iata', default="PUS")
@click.option('--to', 'to_iata', default="BKK")
@click.option('--depart', 'depart_date', required=True)
@click.option('--return', 'return_date', required=True)
def search(from_iata, to_iata, depart_date, return_date):
    key_idx, api_key = get_serpapi_key()
    if not api_key: return

    out_list = parse_flights(fetch_oneway(api_key, from_iata, to_iata, depart_date), from_iata, to_iata)
    in_list = parse_flights(fetch_oneway(api_key, to_iata, from_iata, return_date), to_iata, from_iata)

    if not out_list or not in_list: return

    best_out = out_list[0]
    best_in = in_list[0]
    total_price = best_out['price_total'] + best_in['price_total']

    # --- 1. 구글 시트에 데이터 누적 기록 ---
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    log_row = [
        now_str, 
        best_out['price_total'], best_out['airline'],
        best_in['price_total'], best_in['airline'],
        total_price
    ]
    update_gsheet(log_row)

    # --- 2. 딜 등급 평가 ---
    status_msg = "🔴 비쌈"
    if total_price < 900000: status_msg = "💎 대박 특가 (역대급)"
    elif total_price < 1000000: status_msg = "🔥 구매 권장 (좋은 가격)"
    elif total_price < 1100000: status_msg = "✅ 평균 수준"

    # --- 3. 알림 발송 조건 ---
    is_alert = (total_price < 1000000) or (best_out['price_total'] <= 470000) or (best_in['price_total'] <= 470000)

    if is_alert:
        msg = f"🔔 *[특가 발견] {status_msg}*\n\n"
        msg += f"🛫 *가는 편 ({depart_date[5:]})*\n"
        msg += f"1. {best_out['airline']} ({best_out['time_info']})\n   └ 2인 {best_out['price_total']:,}원 (비행: {best_out['duration']})\n\n"
        msg += f"🛬 *오는 편 ({return_date[5:]})*\n"
        msg += f"1. {best_in['airline']} ({best_in['time_info']})\n   └ 2인 {best_in['price_total']:,}원 (비행: {best_in['duration']})\n\n"
        msg += f"💰 *합계(2인): {total_price:,}원*\n"
        
        direct_link = f"https://www.google.com/travel/flights?q=Flights%20to%20{to_iata}%20from%20{from_iata}%20on%20{depart_date}%20through%20{return_date}"
        msg += f"🔗 [구글 플라이트에서 예약하기]({direct_link})"
        
        send_telegram(msg)
    
    # --- 4. 상세 로그 (터미널) ---
    click.echo(f"[{datetime.now().strftime('%H:%M:%S')}] 🔑 {key_idx}번 키 사용 중")
    click.echo("=" * 45)
    click.echo(f"📊 현재 상태: {status_msg}")
    click.echo(f"💰 2인 총합: {total_price:,}원 (1인당 {total_price // 2:,}원)")
    click.echo("-" * 45)
    click.echo(f"🛫 가는 편 최저: {best_out['airline']} | {best_out['time_info']} | {best_out['price_total']:,}원")
    click.echo(f"🛬 오는 편 최저: {best_in['airline']} | {best_in['time_info']} | {best_in['price_total']:,}원")
    
    diff = total_price - 1000000
    if diff > 0:
        click.echo(f"📉 목표가(100만)까지 {diff:,}원 더 내려가야 함")
    click.echo("=" * 45)

if __name__ == '__main__':
    cli()
