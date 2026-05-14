import os
import click
import requests
import random
from datetime import datetime

def send_telegram(message):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("CHAT_ID")
    if not token or not chat_id: return
    # disable_web_page_preview=True 를 추가해서 텔레그램 미리보기 창이 지저분해지는 걸 막습니다.
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": True})

def get_serpapi_key():
    """등록된 모든 키(1~8번)를 로테이션하여 사용"""
    keys = [os.getenv(f"SERPAPI_KEY_{i}") for i in range(1, 9)]
    valid_keys = [k for k in keys if k]
    return random.choice(valid_keys) if valid_keys else None

def fetch_oneway(api_key, from_iata, to_iata, date_str):
    """구글 플라이트에서 2인 편도 정보를 가져옵니다."""
    params = {
        "engine": "google_flights",
        "departure_id": from_iata,
        "arrival_id": to_iata,
        "outbound_date": date_str,
        "type": 2,  # 편도 검색
        "adults": 2, 
        "currency": "KRW",
        "hl": "ko",
        "api_key": api_key
    }
    try:
        data = requests.get("https://serpapi.com/search", params=params).json()
        return data.get("best_flights", []) + data.get("other_flights", [])
    except Exception as e:
        print(f"API 에러 발생: {e}")
        return []  # 뭔가 잘못돼도 봇이 죽지 않고 빈 배열 반환

def parse_flights(flight_data):
    """가장 저렴한 비행기 정보 3개만 추출 (1인당 가격 포함)"""
    parsed = []
    for item in flight_data:
        price = item.get("price", 0) # 2인 총액
        flights = item.get("flights", [])
        if not flights or price == 0: continue
        
        first = flights[0]
        last = flights[-1]
        
        dep_time = datetime.strptime(first.get("departure_airport", {}).get("time"), "%Y-%m-%d %H:%M")
        arr_time = datetime.strptime(last.get("arrival_airport", {}).get("time"), "%Y-%m-%d %H:%M")

        parsed.append({
            "airline": first.get("airline", "Unknown"),
            "time": f"{dep_time.strftime('%H:%M')}~{arr_time.strftime('%H:%M')}",
            "price_total": price,
            "price_per_person": price // 2  # 1인당 가격 계산
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

    # 1. 가는 편 & 오는 편 검색
    out_list = parse_flights(fetch_oneway(api_key, from_iata, to_iata, depart_date))
    in_list = parse_flights(fetch_oneway(api_key, to_iata, from_iata, return_date))

    if not out_list or not in_list:
        click.echo("⚠️ 검색 결과가 없습니다.")
        return

    # 2. 최저가 기준 계산
    best_out = out_list[0]
    best_in = in_list[0]
    total_price = best_out['price_total'] + best_in['price_total']

    # 3. 알림 조건 체크 (왕복 100만 원 미만 OR 한쪽 편도 47만 원 이하)
    is_alert = (total_price < 1000000) or (best_out['price_total'] <= 470000) or (best_in['price_total'] <= 470000)

    if is_alert:
        msg = f"🔔 *[특가 발견] 방콕 레이더 보고*\n"
        if total_price < 1000000:
            msg += f"🔥 *왕복 총액 100만 원 미만 달성!*\n"
        elif best_out['price_total'] <= 470000 or best_in['price_total'] <= 470000:
            msg += f"✅ *편도 47만 원 이하 특가 발견!*\n"
        
        msg += f"\n🛫 *가는 편 ({depart_date[5:]})*\n"
        for i, f in enumerate(out_list, 1):
            msg += f"{i}. {f['airline']} ({f['time']})\n   └ 2인 {f['price_total']:,}원 *(1인 {f['price_per_person']:,}원)*\n"
            
        msg += f"\n🛬 *오는 편 ({return_date[5:]})*\n"
        for i, f in enumerate(in_list, 1):
            msg += f"{i}. {f['airline']} ({f['time']})\n   └ 2인 {f['price_total']:,}원 *(1인 {f['price_per_person']:,}원)*\n"
            
        msg += f"\n💡 *최종 왕복 조합 (2인)*: 약 *{total_price:,}원* *(1인 {total_price // 2:,}원)*\n\n"
        
        # 4. 구글 플라이트 직행 링크 (해당 날짜, 출발지, 도착지 세팅된 왕복 검색창)
        direct_link = f"https://www.google.com/travel/flights?q=Flights%20to%20{to_iata}%20from%20{from_iata}%20on%20{depart_date}%20through%20{return_date}"
        msg += f"🔗 [👉 조건 세팅된 구글 플라이트로 바로가기]({direct_link})"
        
        send_telegram(msg)
        click.echo("✅ 기준 충족 - 텔레그램 전송 완료")
    else:
        click.echo(f"🐢 기준 미달 (현재 최저가: {total_price:,}원) - 알림 생략")

if __name__ == '__main__':
    cli()
