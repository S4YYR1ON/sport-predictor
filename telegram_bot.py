import os
import json
import requests
from datetime import datetime, timezone
from flask import Flask
import threading
import time

# --- НАСТРОЙКИ TELEGRAM И PINNACLE ---
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
PINNAPI_KEY = os.getenv("PINNAPI_API_KEY")
SENT_FILE = "sent_matches.json"

app = Flask(__name__)

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
    if not TG_TOKEN or not TG_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"Ошибка ТГ: {e}")

def check_upcoming_matches():
    if not PINNAPI_KEY: return
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
        if not start_ts: continue
        
        try:
            clean = start_ts.split(".")[0].replace("Z", "")
            match_time = datetime.fromisoformat(clean).replace(tzinfo=timezone.utc)
        except: continue

        time_left = (match_time - now_utc).total_seconds() / 60.0
        match_id = ev.get("event_id") or ev.get("id") or f"{ev.get('home')}_{ev.get('away')}"

        # Если матч начнется в ближайшие 30 минут
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

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---
@app.route('/')
def home():
    # Эта функция нужна только для того, чтобы Render дал нам ссылку
    # и чтобы UptimeRobot мог её пинговать
    return "Bot is running!"

def background_worker():
    # Этот цикл работает в фоне и проверяет матчи каждые 5 минут
    while True:
        check_upcoming_matches()
        time.sleep(300) # 300 секунд = 5 минут

if __name__ == "__main__":
    # Запускаем фоновую проверку в отдельном потоке
    threading.Thread(target=background_worker, daemon=True).start()
    
    # Запускаем веб-сервер (Render сам подставит нужный порт)
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
