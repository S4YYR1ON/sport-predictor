import os
import requests
from datetime import datetime, timezone, timedelta

# Берем токены из окружения (в GitHub они будут переданы из Secrets)
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
PINNAPI_KEY = os.getenv("PINNAPI_API_KEY")

def send_telegram_message(text):
    if not TG_TOKEN or not TG_CHAT_ID:
        print("Ошибка: не заданы TG_TOKEN или TG_CHAT_ID")
        return
        
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID, 
        "text": text, 
        "parse_mode": "HTML"
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print(f"Ошибка ТГ API: {r.text}")
    except Exception as e:
        print(f"Ошибка отправки в ТГ: {e}")

def check_upcoming_matches():
    if not PINNAPI_KEY:
        print("Ошибка: не задан PINNAPI_API_KEY")
        return

    url = "https://pinnapi.com/kit/v1/prematch/fixtures"
    headers = {"x-portal-apikey": PINNAPI_KEY}
    params = {"sport_id": 2} # Теннис

    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        events_list = data if isinstance(data, list) else data.get("events", data.get("fixtures", []))
    except Exception as e:
        print(f"Ошибка Pinnapi: {e}")
        return

    now_utc = datetime.now(timezone.utc)
    matches_found = 0
    
    for ev in events_list:
        start_ts = ev.get("start") or ev.get("starts") or ev.get("start_time") or ""
        if not start_ts: 
            continue
        
        try:
            # Парсим время (точно так же, как в sources.py)
            clean = start_ts.split(".")[0].replace("Z", "")
            match_time = datetime.fromisoformat(clean).replace(tzinfo=timezone.utc)
        except Exception:
            continue

        # Считаем, сколько минут осталось до матча
        time_left = (match_time - now_utc).total_seconds() / 60.0

        # Если матч начнется через 15 минут (плюс-минус 2 минуты)
        if 13 <= time_left <= 17:
            home = ev.get("home")
            away = ev.get("away")
            
            # Ищем кэфы Pinnacle в структуре periods (как мы делали в sources.py)
            odds_home = "?"
            odds_away = "?"
            periods = ev.get("periods") or {}
            main = periods.get("num_0") or {}
            ml = main.get("money_line")
            if isinstance(ml, dict):
                odds_home = ml.get("home", "?")
                odds_away = ml.get("away", "?")
            
            msg = (
                f"🎾 <b>Скоро матч!</b>\n"
                f"⏰ Начало через {int(time_left)} мин.\n"
                f"🏆 <b>{home}</b> — <b>{away}</b>\n"
                f"📊 Pinnacle: {odds_home} / {odds_away}\n\n"
                f"👉 <i>Зайди в BetBoom и проверь Value!</i>"
            )
            send_telegram_message(msg)
            matches_found += 1
            
    print(f"Проверка завершена. Отправлено уведомлений: {matches_found}")

if __name__ == "__main__":
    check_upcoming_matches()
