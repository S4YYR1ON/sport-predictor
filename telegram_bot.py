import os
import json
import requests
from datetime import datetime, timezone

TG_TOKEN = os.getenv("TG_TOKEN")
# Сюда можно вписать несколько ID через запятую: "123456,789012"
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
    
    for ev in events_list:
        home = ev.get("home")
        away = ev.get("away")
        if not home or not away: 
            continue
            
        # ФИЛЬТР 1: Отсекаем рынки на Тоталы (Games/Sets)
        if "(Games)" in home or "(Games)" in away or "(Sets)" in home or "(Sets)" in away:
            continue
            
        # ФИЛЬТР 2: Отсекаем парные матчи
        if "/" in home or "/" in away:
            continue

        start_ts = ev.get("start") or ev.get("starts")
        if not start_ts: 
            continue
        
        try:
            clean = start_ts.split(".")[0].replace("Z", "")
            match_time = datetime.fromisoformat(clean).replace(tzinfo=timezone.utc)
        except: 
            continue

        time_left = (match_time - now_utc).total_seconds() / 60.0
        match_id = ev.get("event_id") or ev.get("id") or f"{home}_{away}"

        # ФИЛЬТР 3: Жестко за 5 минут (окно от 1 до 5, чтобы не пропустить из-за задержек GitHub)
        if 0 < time_left <= 5 and match_id not in sent_set:
            
            odds_home, odds_away = "?", "?"
            periods = ev.get("periods") or {}
            main = periods.get("num_0") or {}
            ml = main.get("money_line")
            if isinstance(ml, dict):
                odds_home = ml.get("home", "?")
                odds_away = ml.get("away", "?")
            
            # Округляем кэфы для красоты
            try:
                o_h = f"{float(odds_home):.2f}"
                o_a = f"{float(odds_away):.2f}"
            except:
                o_h, o_a = odds_home, odds_away
                
            msg = (
                f"🚨 <b>Матч через 5 минут!</b> 🚨\n"
                f"🏆 <b>{home}</b> — <b>{away}</b>\n"
                f"📊 Pinnacle: <b>{o_h}</b> / <b>{o_a}</b>\n\n"
                f"👉 <i>Зайди в BetBoom! Сравни кэфы и ставь.</i>"
            )
            send_telegram_message(msg)
            sent_set.add(match_id)
            
    save_sent(sent_set)
    print(f"Проверка завершена. Отправлено: {len(sent_set)}")

if __name__ == "__main__":
    check_upcoming_matches()
