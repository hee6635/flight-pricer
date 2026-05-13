import os
import click
import yaml
import requests
import json
from datetime import datetime, timedelta
from tabulate import tabulate

# --- 사용자 맞춤 설정 구역 ---
ANCHOR_DATE = datetime(2026, 5, 15)  # 주간 1일차 기준일
WORK_CYCLE = ["주간", "주간", "휴무", "휴무", "야간", "야간", "휴무", "휴무"] # 8일 주기
# -------------------------

CONFIG_DIR = os.path.expanduser("~/.config/flight-pricer")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.yaml")
API_BASE_URL = "https://api.duffel.com/air/offer_requests"

def send_telegram(message):
    """텔레그램으로 메시지 전송"""
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("CHAT_ID")
    
    if not token or not chat_id:
        click.echo("⚠️ 텔레그램 환경변수(토큰/CHAT_ID)가 없습니다. (화면에만 출력됩니다)")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        response = requests.post(url, data={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"})
        if response.status_code == 200:
            click.echo("✅ 텔레그램 특가 알림 전송 완료!")
        else:
            click.echo(f"❌ 텔레그램 전송 실패: {response.text}")
    except Exception as e:
        click.echo(f"❌ 텔레그램 전송 중 에러 발생: {e}")

def get_api_key():
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = yaml.safe_load(f)
            return config.get('api_key')
    except (FileNotFoundError, yaml.YAMLError):
        return None

def get_work_status(date_obj):
    """특정 날짜의 근무 상태와 주기상 위치(0~7) 반환"""
    days_diff = (date_obj.replace(hour=0, minute=0, second=0, microsecond=0) - ANCHOR_DATE).days
    pos = days_diff % 8
    return WORK_CYCLE[pos], pos

def calculate_leave_days(dep_date_str, ret_date_str):
    """여행 기간 중 소모되는 연차(주간/야간 근무일) 개수 계산"""
    start = datetime.strptime(dep_date_str, "%Y-%m-%d")
    end = datetime.strptime(ret_date_str, "%Y-%m-%d")
    leave_count = 0
    curr = start
    while curr <= end:
        status, _ = get_work_status(curr)
        if status in ["주간", "야간"]:
            leave_count += 1
        curr += timedelta(days=1)
    return leave_count

def format_datetime(dt_string):
    if not dt_string: return None
    dt_obj = datetime.fromisoformat(dt_string.replace('Z', ''))
    return dt_obj

def display_offers(offers, dep_date, ret_date):
    headers = ["Airline", "Flight No.", "Depart", "Arrive", "Leave", "Price"]
    table_data = []
    
    leave_needed = calculate_leave_days(dep_date, ret_date)
    telegram_msg = f"🎯 *나트랑 특가 정찰 보고 ({dep_date} ~ {ret_date})*\n\n"
    found_valid_flight = False

    for offer in offers:
        airline = offer['owner']['name']
        price_val = float(offer['total_amount'])
        price_str = f"{price_val:,.0f} {offer['total_currency']}"
        
        if not offer['slices']: continue
        
        outbound = offer['slices'][0]['segments'][0]
        inbound = offer['slices'][1]['segments'][0] if len(offer['slices']) > 1 else None
        
        dep_time = format_datetime(outbound.get('departing_at'))
        ret_time = format_datetime(inbound.get('departing_at')) if inbound else None

        # --- 근무표 필터링 로직 ---
        if not dep_time: continue
        
        _, dep_pos = get_work_status(dep_time)
        # 야간 퇴근 당일(주기 7일차, index 6)은 오전 11시 이후 출발만 가능
        if dep_pos == 6 and dep_time.hour < 11:
            continue
            
        # 복귀 비행기(나트랑 출발)는 밤 21시(9 PM) 이후여야 함
        if ret_time and ret_time.hour < 21:
            continue

        found_valid_flight = True
        flight_no = f"{outbound['marketing_carrier']['iata_code']}{outbound['marketing_carrier_flight_number']}"
        
        dep_str = dep_time.strftime('%m/%d %H:%M')
        ret_str = ret_time.strftime('%m/%d %H:%M') if ret_time else "N/A"

        table_data.append([airline, flight_no, dep_str, ret_str, f"{leave_needed}개", price_str])
        
        # 텔레그램용 메시지 조립
        telegram_msg += f"✈️ *{airline}* ({flight_no})\n💰 {price_str}\n📅 {dep_str} 출발\n🌴 연차 {leave_needed}개 필요\n\n"

    if found_valid_flight:
        # 1. 로그 창에 표 그리기
        click.echo(tabulate(table_data, headers=headers, tablefmt="grid"))
        # 2. 텔레그램으로 발송하기
        telegram_msg += "🔗 [구글 플라이트 확인](https://www.google.com/travel/flights)\n"
        send_telegram(telegram_msg)
    else:
        click.echo("⚠️ 조건(근무표/시간)에 맞는 항공권이 없습니다.")

@click.group()
def cli(): pass

@cli.command()
@click.option('--from', 'from_iata', default="PUS", help='출발 공항 (기본: PUS/김해)')
@click.option('--to', 'to_iata', default="CXR", help='도착 공항 (기본: CXR/나트랑)')
@click.option('--depart', 'depart_date', required=True, help='출발일 (YYYY-MM-DD)')
@click.option('--return', 'return_date', required=True, help='귀국일 (YYYY-MM-DD)')
def search(from_iata, to_iata, depart_date, return_date):
    """4인 가족 & 근무표 맞춤형 항공권 검색"""
    api_key = get_api_key()
    if not api_key:
        click.echo("API 키를 먼저 설정하세요.")
        return

    headers = {
        "Content-Type": "application/json",
        "Duffel-Version": "v2",
        "Authorization": f"Bearer {api_key}"
    }

    # 4인 가족 설정 (성인 2, 아동 2)
    passenger_list = [{"type": "adult"}, {"type": "adult"}, {"type": "child"}, {"type": "child"}]

    payload = {
        "data": {
            "slices": [
                {"origin": from_iata, "destination": to_iata, "departure_date": depart_date},
                {"origin": to_iata, "destination": from_iata, "departure_date": return_date}
            ],
            "passengers": passenger_list,
            "cabin_class": "economy"
        }
    }
    
    click.echo(f"🔍 {depart_date} ~ {return_date} (4인 가족) 검색 중...")
    
    try:
        response = requests.post(API_BASE_URL, headers=headers, json=payload)
        response.raise_for_status()
        offers = response.json().get('data', {}).get('offers', [])
        display_offers(offers, depart_date, return_date)
    except Exception as e:
        click.echo(f"오류 발생: {e}")

if __name__ == '__main__':
    cli()

