import os
import click
import yaml
import requests
import json
from datetime import datetime, timedelta
from tabulate import tabulate

# --- 사용자 맞춤 설정 ---
ANCHOR_DATE = datetime(2026, 5, 15)
WORK_CYCLE = ["주간", "주간", "휴무", "휴무", "야간", "야간", "휴무", "휴무"]
# ----------------------

CONFIG_DIR = os.path.expanduser("~/.config/flight-pricer")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.yaml")
API_BASE_URL = "https://api.duffel.com/air/offer_requests"

def send_telegram(message):
    """텔레그램으로 메시지 전송"""
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("CHAT_ID")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            requests.post(url, data={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"})
        except Exception as e:
            print(f"텔레그램 전송 실패: {e}")

# ... (기존 get_api_key, get_work_status, calculate_leave_days, format_datetime 함수는 유지) ...

def display_offers(offers, dep_date, ret_date):
    headers = ["Airline", "Flight No.", "Depart", "Arrive", "Leave", "Price"]
    table_data = []
    leave_needed = calculate_leave_days(dep_date, ret_date)
    telegram_msg = f"🎯 *나트랑 특가 정찰 보고 ({dep_date} ~ {ret_date})*\n\n"

    for offer in offers:
        airline = offer['owner']['name']
        price_val = float(offer['total_amount'])
        price_str = f"{price_val:,.0f} {offer['total_currency']}"
        
        if not offer['slices']: continue
        outbound = offer['slices'][0]['segments'][0]
        inbound = offer['slices'][1]['segments'][0] if len(offer['slices']) > 1 else None
        
        dep_time = format_datetime(outbound.get('departing_at'))
        ret_time = format_datetime(inbound.get('departing_at')) if inbound else None

        # 근무표 필터
        _, dep_pos = get_work_status(dep_time)
        if dep_pos == 6 and dep_time.hour < 11: continue
        if ret_time and ret_time.hour < 21: continue

        flight_no = f"{outbound['marketing_carrier']['iata_code']}{outbound['marketing_carrier_flight_number']}"
        
        table_data.append([airline, flight_no, dep_time.strftime('%m/%d %H:%M'), 
                           ret_time.strftime('%m/%d %H:%M') if ret_time else "N/A", 
                           f"{leave_needed}개", price_str])
        
        # 텔레그램용 메시지 조립
        telegram_msg += f"✈️ *{airline}* ({flight_no})\n💰 {price_str}\n📅 {dep_time.strftime('%m/%d %H:%M')} 출발\n🌴 연차 {leave_needed}개 필요\n\n"

    if table_data:
        # 화면 출력
        click.echo(tabulate(table_data, headers=headers, tablefmt="grid"))
        # 텔레그램 전송
        send_telegram(telegram_msg + "🔗 [구글 플라이트 확인](https://www.google.com/travel/flights)")
    else:
        click.echo("⚠️ 조건에 맞는 항공권이 없습니다.")

# ... (나머지 cli, config, search 함수 유지) ...
