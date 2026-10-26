import os
import json
import requests
import time
from datetime import datetime, timezone
from livetennisapi import LiveTennisAPI

TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_IDS_STR = os.getenv("TG_CHAT_ID", "")
TG_CHAT_IDS = [cid.strip() for cid in TG_CHAT_IDS_STR.split(",") if cid.strip()]
PINNAPI_KEY = os.getenv("PINNAPI_API_KEY")
LIVETENNIS_KEY = os.getenv("LIVETENNIS_API_KEY") # НОВЫЙ КЛЮЧ
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

# Функция для получения точного времени из Live Tennis API
def get_livetennis_times():
    times = {}
    if not LIVETENNIS_KEY: return times
    try:
        with LiveTennisAPI(api_key=LIVETENNIS_KEY) as client:
            fixtures = client.list_fixtures(limit=200)
            for match in fixtures:
                tour = str(getattr(match, 'tour', '')).lower()
                if tour not in ['atp', 'wta']: continue
                
                p1 = str(getattr(match, 'player1_name', '')).lower()
                p2 = str(getattr(match, 'player2_name', '')).lower()
                
                # Берем только фамилии (последнее слово) для совмещения с Pinnacle
                p1_last = p1.split()[-1] if p1 else ""
                p2_last = p2.split()[-1] if p2 else ""
                
                start_time_raw = getattr(match, 'start_time', None)
                if start_time_raw:
                    clean_time = str(start_time_raw).replace("Z", "+00:00")
                    dt_utc = datetime.fromisoformat(clean_time)
                    if dt_utc.tzinfo is None:
                        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
                    # Ключ: "фамилия1_фамилия2"
                    times[f"{p1_last}_{p2_last}"] = dt_utc
    except Exception as e:
        print(f"Ошибка LiveTennis: {e}")
    return times

def check_upcoming_matches(sent_set, lt_times):
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

        # Ищем время в Live Tennis по фамилиям
        h_last = home.lower().split()[-1]
        a_last = away.lower().split()[-1]
        
        lt_time = lt_times.get(f"{h_last}_{a_last}") or lt_times.get(f"{a_last}_{h_last}")
        
        # Если Live Tennis знает точное время - используем его. Иначе - время Pinnacle
        if lt_time:
            match_time = lt_time
        else:
            start_ts = ev.get("start") or ev.get("starts")
            if not start_ts: continue
            try:
                clean = start_ts.split(".")[0].replace("Z", "")
                match_time = datetime.fromisoformat(clean).replace(tzinfo=timezone.utc)
            except: continue

        time_left = (match_time - now_utc).total_seconds() / 60.0
        match_id = ev.get("event_id") or ev.get("id") or f"{home}_{away}"

        # Окно от 1 до 6 минут
        if 0 < time_left <= 6 and match_id not in sent_set:
            odds_home, odds_away = "?", "?"
            ml = (ev.get("periods", {}).get("num_0", {}).get("money_line", {}))
            if isinstance(ml, dict):
                odds_home, odds_away = ml.get("home", "?"), ml.get("away", "?")
            
            try:
                o_h, o_a = float(odds_home), float(odds_away)
                if min(o_h, o_a) < 1.40 or max(o_h, o_a) > 15.0: continue
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
    print("Бот запущен в режиме 24/7 с синхронизацией Live Tennis...")
    sent_set = load_sent()
    
    # Работаем 5.5 часов (19800 секунд)
    start_time = time.time()
    lt_cache = {}
    last_lt_update = 0
    
    while time.time() - start_time < 19800:
        current_time = time.time()
        
        # Обновляем время из Live Tennis только раз в 20 минут (1200 секунд), чтобы не спалить лимиты
        if current_time - last_lt_update > 1200:
            print("Обновляю расписание из Live Tennis API...")
            lt_cache = get_livetennis_times()
            last_lt_update = current_time
            
        check_upcoming_matches(sent_set, lt_cache)
        time.sleep(300) # Спим ровно 5 минут
        
    print("Цикл завершен. GitHub запустит следующий.")
