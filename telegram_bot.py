import os
import requests
from datetime import datetime, timezone, timedelta

# Берем токены из настроек (на GitHub они будут в Secrets)
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
PINNAPI_KEY = os.getenv("PINNAPI_API_KEY")

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Ошибка отправки в ТГ: {e}")

def check_upcoming_matches():
    # Примерный эндпоинт Pinnapi (замени на свой рабочий)
    url = "https://pinnapi.com/kit/v1/prematch/fixtures"
    headers = {"x-portal-apikey": PINNAPI_KEY}
    params = {"sport_id": 2} # Теннис

    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        events = r.json().get("events", []) # или как там у них в JSON
    except Exception as e:
        print(f"Ошибка Pinnapi: {e}")
        return

    now_utc = datetime.now(timezone.utc)
    
    for ev in events:
        start_ts = ev.get("start") or ev.get("starts")
        if not start_ts: continue
        
        try:
            # Парсим время начала матча
            clean = start_ts.split(".")[0].replace("Z", "")
            match_time = datetime.fromisoformat(clean).replace(tzinfo=timezone.utc)
        except:
            continue

        # Считаем, сколько минут осталось до матча
        time_left = (match_time - now_utc).total_seconds() / 60.0

        # Если матч начнется через 15 минут (плюс-минус 2 минуты)
        if 13 <= time_left <= 17:
            home = ev.get("home")
            away = ev.get("away")
            
            # Достаем кэф Pinnacle (для ориентира)
            odds_home = ev.get("odds_home", "?")
            odds_away = ev.get("odds_away", "?")
            
            msg = (
                f"🎾 <b>Скоро матч!</b>\n"
                f"⏰ Начало через {int(time_left)} мин.\n"
                f"🏆 {home} — {away}\n"
                f"📊 Pinnacle: {odds_home} / {odds_away}\n\n"
                f"👉 <i>Зайди в BetBoom и проверь Value!</i>"
            )
            send_telegram_message(msg)
            print(f"Отправлено уведомление: {home} - {away}")

if __name__ == "__main__":
    check_upcoming_matches()
