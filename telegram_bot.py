import os
import json
import requests
from datetime import datetime, timezone

TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_IDS_STR = os.getenv("TG_CHAT_ID", "")
TG_CHAT_IDS = [cid.strip() for cid in TG_CHAT_IDS_STR.split(",") if cid.strip()]
PINNAPI_KEY = os.getenv("PINNAPI_API_KEY")
SENT_FILE = "sent_matches.json"

def load_sent():
    if os.path.exists(SENT_FILE):
        try:
            with open(SENT_FILE, "r") as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_sent(sent_set):
    with open(SENT_FILE, "w") as f:
        json.dump(list(sent_set), f)

def send_telegram_message(text):
    if not TG_TOKEN or not TG_CHAT_IDS: 
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    for chat_id in TG_CHAT_IDS:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"Ошибка ТГ для {chat_id}: {e}")

def check_upcoming_matches():
    if not PINNAPI_KEY: 
        return
    url = "https://pinnapi.com/kit/v1/prematch/fixtures"
    headers = {"x-portal-apikey": PINNAPI_KEY}
    
    try:
        r = requests.get(url, headers=headers, params={"sport_id": 2}, timeout=15)
        data = r.json()
        events_list = data if isinstance(data, list) else data.get("events", data.get("fixtures", []))
    except Exception as e:
        print(f"Ошибка Pinnapi: {e}")
        return

    now_utc = datetime.now(timezone.utc)
    sent_set = load_sent()
    matches_found = 0
    
    for ev in events_list:
        start_ts = ev.get("start") or ev.get("starts")
        if not start_ts: 
            continue
        
        try:
            clean = start_ts.split(".")[0].replace("Z", "")
            match_time = datetime.fromisoformat(clean).replace(tzinfo=timezone.utc)
        except: 
            continue

        time_left = (match_time - now_utc).total_seconds() / 60.0
        match_id = ev.get("event_id") or ev.get("id") or f"{ev.get('home')}_{ev.get('away')}"

        if 0 < time_left <= 30 and match_id not in sent_set:
            home, away = ev.get("home"), ev.get("away")
            odds_home, odds_away = "?", "?"
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
            sent_set.add(match_id)
            matches_found += 1
            
    save_sent(sent_set)
    print(f"Проверка завершена. Отправлено: {matches_found}")

if __name__ == "__main__":
    # Бесконечный цикл проверки каждые 5 минут
    import time
    while True:
        check_upcoming_matches()
        time.sleep(300) # 5 минут
