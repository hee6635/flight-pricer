import os
import click
import requests
import random
from datetime import datetime

def send_telegram(message):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("CHAT_ID")
    if not token or not chat_id: return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": True})

def get_serpapi_key():
    keys = [os.getenv(f"SERPAPI_KEY_{i}") for i in range(1, 9)]
    valid_keys = [k for k in keys if k]
    return random.choice(valid_keys) if valid_keys else None

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
        if not flights or price == 0 or len(flights) != 1: continue # 직항만
        
        f = flights[0]
        if f.get("departure_airport", {}).get("id") != expected_from: continue
            
        dep_time = datetime.strptime(f.get("departure_airport", {}).get("time"), "%Y-%m-%d %H:%M")
        arr_time = datetime.strptime(f.get("arrival_airport", {}).get("time"), "%Y-%m-%d %H:%M")

        parsed.append({
            "airline": f.get("airline", "Unknown"),
            "time": f"{dep_time.strftime('%H:%M')}~{arr_time.strftime('%H:%M')}",
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
    api_key = get_serpapi_key()
    if not api_key: return

    out_list = parse_flights(fetch_oneway(api_key, from_iata, to_iata, depart_date), from_iata, to_iata)
    in_list = parse_flights(fetch_oneway(api_key, to_iata, from_iata, return_date), to_iata, from_iata)

    if not out_list or not in_list: return

    best_out = out_list[0]
    best_in = in_list[0]
    total_price = best_out['price_total'] + best_in['price_total']

    # 알림 조건: 왕복 100만 미만 OR 가는 편 47만 이하 OR 오는 편 47만 이하
    is_alert = (total_price < 1000000) or (best_out['price_total'] <= 470000) or (best_in['price_total'] <= 470000)

    if is_alert:
        # 알림 사유 특정
        reason = ""
        if total_price < 1000000: reason = "🔥 왕복 총액 100만 원 미만 달성!"
        elif best_out['price_total'] <= 470000: reason = "🛫 가는 편 47만 원 이하 특가 발견!"
        else: reason = "🛬 오는 편 47만 원 이하 특가 발견!"

        msg = f"🔔 *[특가 보고] 방콕 직항 레이더*\n{reason}\n\n"
        
        msg += f"🛫 *가는 편 ({depart_date[5:]})*\n"
        for i, f in enumerate(out_list, 1):
            mark = "⭐" if f['price_total'] <= 470000 else ""
            msg += f"{i}. {f['airline']} {mark}\n   └ {f['time']} / 2인 {f['price_total']:,}원 (1인 {f['price_per']:,})\n"
            
        msg += f"\n🛬 *오는 편 ({return_date[5:]})*\n"
        for i, f in enumerate(in_list, 1):
            mark = "⭐" if f['price_total'] <= 470000 else ""
            msg += f"{i}. {f['airline']} {mark}\n   └ {f['time']} / 2인 {f['price_total']:,}원 (1인 {f['price_per']:,})\n"
            
        msg += f"\n💰 *최저가 조합 총액 (2인)*: 약 *{total_price:,}원*\n"
        msg += f"   *(1인 환산 시: 약 {total_price // 2:,}원)*\n\n"
        
        direct_link = f"https://www.google.com/travel/flights?q=Flights%20to%20{to_iata}%20from%20{from_iata}%20on%20{depart_date}%20through%20{return_date}"
        msg += f"🔗 [구글 플라이트에서 지금 예약]({direct_link})"
        
        send_telegram(msg)
        click.echo(f"✅ 알림 전송 완료 (이유: {reason})")
    else:
        click.echo(f"🐢 기준 미달 (최저 합계: {total_price:,}원) - 알림 생략")

if __name__ == '__main__':
    cli()
