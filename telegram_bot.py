import os
import json
import requests
import time
from datetime import datetime, timezone

TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_IDS_STR = os.getenv("TG_CHAT_ID", "")
TG_CHAT_IDS = [cid.strip() for cid in TG_CHAT_IDS_STR.split(",") if cid.strip()]
PINNAPI_KEY = os.getenv("PINNAPI_API_KEY")
SENT_FILE = "sent_matches.json"

def load_sent():
    if os.path.exists(SENT_FILE):
        try:
            with open(SENT_FILE, "r") as f: return set(json.load(f))
        except: return set()
    return set()

def save_sent(sent_set):
    with open(SENT_FILE, "w") as f: json.dump(list(sent_set), f)

def send_telegram_message(text):
    if not TG_TOKEN or not TG_CHAT_IDS: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    for chat_id in TG_CHAT_IDS:
        try:
            requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=10)
        except Exception as e:
            print(f"Ошибка ТГ: {e}")

def check_upcoming_matches(sent_set):
    if not PINNAPI_KEY: return
    
    url = "https://pinnapi.com/kit/v1/prematch/fixtures"
    headers = {"x-portal-apikey": PINNAPI_KEY}
    
    try:
        r = requests.get(url, headers=headers, params={"sport_id": 2}, timeout=15)
        data = r.json()
        events_list = data if isinstance(data, list) else data.get("events", [])
    except Exception as e:
        print(f"Ошибка Pinnapi: {e}")
        return

    now_utc = datetime.now(timezone.utc)
    matches_found = 0
    
    for ev in events_list:
        home, away = ev.get("home"), ev.get("away")
        if not home or not away: continue
        if "(Games)" in home or "(Games)" in away or "(Sets)" in home or "(Sets)" in away: continue
        if "/" in home or "/" in away: continue

        start_ts = ev.get("start") or ev.get("starts")
        if not start_ts: continue
        
        try:
            clean = start_ts.split(".")[0].replace("Z", "")
            match_time = datetime.fromisoformat(clean).replace(tzinfo=timezone.utc)
        except: continue

        time_left = (match_time - now_utc).total_seconds() / 60.0
        match_id = ev.get("event_id") or ev.get("id") or f"{home}_{away}"

        # Окно от 1 до 10 минут
        if 0 < time_left <= 10 and match_id not in sent_set:
            odds_home, odds_away = "?", "?"
            ml = (ev.get("periods", {}).get("num_0", {}).get("money_line", {}))
            if isinstance(ml, dict):
                odds_home, odds_away = ml.get("home", "?"), ml.get("away", "?")
            
            try:
                o_h, o_a = float(odds_home), float(odds_away)
                if min(o_h, o_a) < 1.15 or max(o_h, o_a) > 15.0: continue
                o_h_str, o_a_str = f"{o_h:.2f}", f"{o_a:.2f}"
            except:
                o_h_str, o_a_str = odds_home, odds_away
                
            mins_left = max(1, int(time_left))
            msg = (
                f"🚨 <b>Матч через {mins_left} мин!</b> 🚨\n"
                f"🏆 <b>{home}</b> — <b>{away}</b>\n"
                f"📊 Pinnacle: <b>{o_h_str}</b> / <b>{o_a_str}</b>\n\n"
                f"👉 <i>Зайди в BetBoom!</i>"
            )
            send_telegram_message(msg)
            sent_set.add(match_id)
            matches_found += 1
            
    if matches_found > 0:
        print(f"Отправлено: {matches_found}")
        save_sent(sent_set)

if __name__ == "__main__":
    print("Бот запущен в режиме 24/7 (5.5 часов на цикл)...")
    sent_set = load_sent()
    
    # Работаем 5.5 часов (19800 секунд)
    start_time = time.time()
    while time.time() - start_time < 19800:
        check_upcoming_matches(sent_set)
        time.sleep(300) # Спим ровно 5 минут
        
    print("Цикл завершен. GitHub запустит следующий.")
