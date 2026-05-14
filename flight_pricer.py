import os
import click
import requests
import random
from datetime import datetime, timedelta
from tabulate import tabulate

# --- 아빠의 근무 일정 기반 설정 ---
ANCHOR_DATE = datetime(2026, 5, 15)  # 주간 1일차 기준일
WORK_CYCLE = ["주간", "주간", "휴무", "휴무", "야간", "야간", "휴무", "휴무"] #
# -------------------------

def send_telegram(message):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("CHAT_ID")
    if not token or not chat_id: return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"})

def get_serpapi_key():
    """등록된 모든 키(1~8번)를 자동으로 인식하여 랜덤 사용"""
    keys = [os.getenv(f"SERPAPI_KEY_{i}") for i in range(1, 9)]
    valid_keys = [k for k in keys if k]
    return random.choice(valid_keys) if valid_keys else None

def get_work_status(date_obj):
    days_diff = (date_obj.replace(hour=0, minute=0, second=0, microsecond=0) - ANCHOR_DATE).days
    pos = days_diff % 8
    return WORK_CYCLE[pos], pos

def calculate_leave_days(dep_date_str, ret_date_str):
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

@click.group()
def cli(): pass

@cli.command()
@click.option('--from', 'from_iata', default="PUS")
@click.option('--to', 'to_iata', default="BKK")
@click.option('--depart', 'depart_date', required=True)
@click.option('--return', 'return_date', required=True)
def search(from_iata, to_iata, depart_date, return_date):
    api_key = get_serpapi_key()
    if not api_key:
        click.echo("⚠️ SERPAPI_KEY가 등록되지 않았습니다.")
        return

    # 성인 2명 실거래가 검색
    params = {
        "engine": "google_flights",
        "departure_id": from_iata,
        "arrival_id": to_iata,
        "outbound_date": depart_date,
        "return_date": return_date,
        "adults": 2, 
        "currency": "KRW",
        "hl": "ko",
        "api_key": api_key
    }

    try:
        data = requests.get("https://serpapi.com/search", params=params).json()
    except Exception as e:
        click.echo(f"❌ 검색 에러: {e}")
        return

    all_flights = data.get("best_flights", []) + data.get("other_flights", [])
    leave_needed = calculate_leave_days(depart_date, return_date)
    
    table_data = []
    telegram_msg = f"⚡ *[긴급] 방콕 특가 사냥 보고 (30분 간격)*\n📅 {depart_date} ~ {return_date}\n🌴 필요 연차: {leave_needed}개\n\n"
    found_valid = False

    for item in all_flights:
        price = item.get("price", 0)
        flights = item.get("flights", [])
        if not flights or price == 0: continue
        
        outbound = flights[0]
        airline = outbound.get("airline", "Unknown")
        dep_time_str = outbound.get("departure_airport", {}).get("time")
        
        try:
            dep_time = datetime.strptime(dep_time_str, "%Y-%m-%d %H:%M")
        except: continue

        # 야간 퇴근 당일(주기 7일차) 오전 출발 필터링
        _, dep_pos = get_work_status(dep_time)
        if dep_pos == 6 and dep_time.hour < 11: continue

        found_valid = True
        price_str = f"{price:,.0f}원"
        dep_str = dep_time.strftime('%m/%d %H:%M')
        
        table_data.append([airline, dep_str, price_str])
        telegram_msg += f"✈️ *{airline}*\n💰 *{price_str}*\n🛫 출발: {dep_str}\n\n"

    if found_valid:
        click.echo(tabulate(table_data, headers=["Airline", "Depart", "Price"], tablefmt="grid"))
        telegram_msg += "🔗 [지금 바로 확인 및 예약](https://www.google.com/travel/flights)"
        send_telegram(telegram_msg)
    else:
        click.echo("⚠️ 조건에 맞는 최저가 항공권이 현재 없습니다.")

if __name__ == '__main__':
    cli()
