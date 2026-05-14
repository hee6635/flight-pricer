import os
import click
import requests
import random
from datetime import datetime, timedelta
from tabulate import tabulate

# --- 아빠의 근무 일정 기반 설정 ---
ANCHOR_DATE = datetime(2026, 5, 15)
WORK_CYCLE = ["주간", "주간", "휴무", "휴무", "야간", "야간", "휴무", "휴무"]

def send_telegram(message):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("CHAT_ID")
    if not token or not chat_id: return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"})

def get_serpapi_key():
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

def fetch_oneway(api_key, from_iata, to_iata, date_str):
    """편도 특가를 검색해서 가져옵니다."""
    params = {
        "engine": "google_flights",
        "departure_id": from_iata,
        "arrival_id": to_iata,
        "outbound_date": date_str,
        "type": 2, # 2 = 편도(One-way)
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

def parse_flights(flight_data, is_outbound=True):
    """검색된 비행기 정보에서 시간과 가격만 깔끔하게 추려냅니다."""
    parsed = []
    for item in flight_data:
        price = item.get("price", 0)
        flights = item.get("flights", [])
        if not flights or price == 0: continue
        
        # 직항/경유 상관없이 첫 출발과 마지막 도착 시간을 가져옴
        first_segment = flights[0]
        last_segment = flights[-1]
        
        airline = first_segment.get("airline", "Unknown")
        dep_str = first_segment.get("departure_airport", {}).get("time")
        arr_str = last_segment.get("arrival_airport", {}).get("time")
        
        if not dep_str or not arr_str: continue
        
        dep_time = datetime.strptime(dep_str, "%Y-%m-%d %H:%M")
        arr_time = datetime.strptime(arr_str, "%Y-%m-%d %H:%M")

        # 가는 편일 때만 주주휴휴야야휴휴 필터 적용
        if is_outbound:
            _, dep_pos = get_work_status(dep_time)
            if dep_pos == 6 and dep_time.hour < 11: continue

        parsed.append({
            "airline": airline,
            "dep_format": dep_time.strftime('%H:%M'),
            "arr_format": arr_time.strftime('%H:%M'),
            "price": price
        })
    
    # 가격순 정렬 후 상위 3개만 반환
    return sorted(parsed, key=lambda x: x["price"])[:3]

@click.group()
def cli(): pass

@cli.command()
@click.option('--from', 'from_iata', default="PUS")
@click.option('--to', 'to_iata', default="BKK")
@click.option('--depart', 'depart_date', required=True)
@click.option('--return', 'return_date', required=True)
def search(from_iata, to_iata, depart_date, return_date):
    api_key = get_serpapi_key()
    if not api_key: return

    # 1. 가는 편(편도) 검색
    out_data = fetch_oneway(api_key, from_iata, to_iata, depart_date)
    out_list = parse_flights(out_data, is_outbound=True)

    # 2. 오는 편(편도) 검색
    in_data = fetch_oneway(api_key, to_iata, from_iata, return_date)
    in_list = parse_flights(in_data, is_outbound=False)

    if not out_list or not in_list:
        click.echo("⚠️ 조건에 맞는 항공권이 부족합니다.")
        return

    leave_needed = calculate_leave_days(depart_date, return_date)
    
    # 3. 텔레그램 메시지 조립
    msg = f"⚡ *[편도 분리] 방콕 초정밀 보고*\n🌴 필요 연차: {leave_needed}개\n\n"
    
    msg += f"🛫 *[가는 편] 부산 ➡️ 방콕* ({depart_date[5:]})\n"
    for i, f in enumerate(out_list, 1):
        msg += f"{i}. {f['airline']} ({f['dep_format']}~{f['arr_format']}) / {f['price']:,}원\n"
        
    msg += f"\n🛬 *[오는 편] 방콕 ➡️ 부산* ({return_date[5:]})\n"
    for i, f in enumerate(in_list, 1):
        msg += f"{i}. {f['airline']} ({f['dep_format']}~{f['arr_format']}) / {f['price']:,}원\n"
        
    best_combo_price = out_list[0]['price'] + in_list[0]['price']
    msg += f"\n💡 *각각 편도 최저가 결제 시 총액*: 약 *{best_combo_price:,}원*"
    
    send_telegram(msg)
    click.echo("✅ 상세 편도 분리 보고 완료")

if __name__ == '__main__':
    cli()
