import os
import json
import requests
import time
from datetime import datetime, timezone, timedelta
from livetennisapi import LiveTennisAPI

TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_IDS_STR = os.getenv("TG_CHAT_ID", "")
TG_CHAT_IDS = [cid.strip() for cid in TG_CHAT_IDS_STR.split(",") if cid.strip()]
PINNAPI_KEY = os.getenv("PINNAPI_API_KEY")
LIVETENNIS_KEY = os.getenv("LIVETENNIS_API_KEY")
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

def get_livetennis_times():
    times = {}
    if not LIVETENNIS_KEY: return times
    try:
        with LiveTennisAPI(api_key=LIVETENNIS_KEY) as client:
            fixtures = client.list_fixtures(limit=200)
            for match in fixtures:
                tour = str(getattr(match, 'tour', '')).lower()
                if tour not in ['atp', 'wta']: continue
                
                p1 = str(getattr(match, 'player1_name', '')).lower().strip()
                p2 = str(getattr(match, 'player2_name', '')).lower().strip()
                
                p1_last = p1.split()[-1] if p1 else ""
                p2_last = p2.split()[-1] if p2 else ""
                if not p1_last or not p2_last: continue
                
                start_time_raw = getattr(match, 'start_time', None)
                if start_time_raw:
                    clean_time = str(start_time_raw).replace("Z", "+00:00")
                    dt_utc = datetime.fromisoformat(clean_time)
                    if dt_utc.tzinfo is None:
                        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
                    times[f"{p1_last}_{p2_last}"] = dt_utc
    except Exception as e:
        print(f"Ошибка LiveTennis: {e}")
    return times

def extract_markets(main_period):
    """Правильное извлечение рынков из структуры Pinnapi (словари с ключами линий)"""
    markets = {
        "ml_home": "?", "ml_away": "?",
        "spread": None,
        "total": None
    }
    
    # 1. Исход
    ml = main_period.get("money_line")
    if isinstance(ml, dict):
        markets["ml_home"] = ml.get("home", "?")
        markets["ml_away"] = ml.get("away", "?")
        
    # 2. Форы (Spreads)
    spreads = main_period.get("spreads")
    if isinstance(spreads, dict) and spreads:
        # Берем первую попавшуюся линию из словаря (обычно она одна основная)
        first_key = list(spreads.keys())[0]
        sp_data = spreads[first_key]
        hdp = sp_data.get("hdp", "")
        h_price = sp_data.get("home", "?")
        a_price = sp_data.get("away", "?")
        
        try:
            h_price = f"{float(h_price):.2f}"
            a_price = f"{float(a_price):.2f}"
        except: pass
        
        markets["spread"] = f"Ф1({hdp}): {h_price} | Ф2({-float(hdp)}): {a_price}"
            
    # 3. Тоталы (Totals)
    totals = main_period.get("totals")
    if isinstance(totals, dict) and totals:
        # Берем первую линию (обычно 2.5 сета)
        first_key = list(totals.keys())[0]
        tot_data = totals[first_key]
        points = tot_data.get("points", "")
        o_price = tot_data.get("over", "?")
        u_price = tot_data.get("under", "?")
        
        try:
            o_price = f"{float(o_price):.2f}"
            u_price = f"{float(u_price):.2f}"
        except: pass
        
        markets["total"] = f"ТМ({points}): {u_price} | ТБ({points}): {o_price}"
            
    return markets

def check_upcoming_matches(sent_set, lt_times):
    if not PINNAPI_KEY: return
    
    url = "https://pinnapi.com/kit/v1/prematch/fixtures"
    headers = {"x-portal-apikey": PINNAPI_KEY}
    
    try:
        r = requests.get(url, headers=headers, params={"sport_id": 2}, timeout=15)
        if r.status_code == 429:
            print("!!! ЛИМИТ ЗАПРОСОВ PINNAPI ИСЧЕРПАН (429) !!!")
            return
        data = r.json()
        events_list = data if isinstance(data, list) else data.get("events", [])
    except Exception as e:
        print(f"Ошибка Pinnapi: {e}")
        return

    now_utc = datetime.now(timezone.utc)
    matches_found = 0
    
    for ev in events_list:
        home = str(ev.get("home", "")).strip()
        away = str(ev.get("away", "")).strip()
        if not home or not away: continue
        if "(Games)" in home or "(Games)" in away or "(Sets)" in home or "(Sets)" in away: continue
        if "/" in home or "/" in away: continue

        status = str(ev.get("status", "")).lower()
        if status in ["finished", "ended", "live", "inprogress", "started", "settled", "cancelled"]:
            continue

        h_parts = home.lower().split()
        a_parts = away.lower().split()
        if not h_parts or not a_parts: continue
        h_last = h_parts[-1]
        a_last = a_parts[-1]

        lt_time = lt_times.get(f"{h_last}_{a_last}") or lt_times.get(f"{a_last}_{h_last}")
        
        if lt_time:
            match_time = lt_time
        else:
            start_ts = ev.get("start") or ev.get("starts")
            if not start_ts: continue
            try:
                clean = start_ts.split(".")[0].replace("Z", "")
                match_time = datetime.fromisoformat(clean).replace(tzinfo=timezone.utc)
            except: continue

        if match_time < now_utc - timedelta(hours=2):
            continue

        time_left = (match_time - now_utc).total_seconds() / 60.0
        match_id = ev.get("event_id") or ev.get("id") or f"{home}_{away}"

        if 0 < time_left <= 12 and match_id not in sent_set: # Окно 15 минут
            periods = ev.get("periods", {})
            main_period = periods.get("num_0", {})
            
            markets = extract_markets(main_period)
            
            try:
                o_h = float(markets["ml_home"])
                o_a = float(markets["ml_away"])
                if min(o_h, o_a) < 1.40 or max(o_h, o_a) > 15.0: continue
                ml_str = f"{o_h:.2f} / {o_a:.2f}"
            except:
                continue

            mins_left = max(1, int(time_left))
            
            # Формируем сообщение
            msg = f"🚨 <b>Матч через {mins_left} мин!</b> 🚨\n"
            msg += f"🏆 <b>{home}</b> — <b>{away}</b>\n\n"
            msg += f"<b>Исход:</b> {ml_str}\n"
            
            if markets["spread"]:
                msg += f"<b>Фора:</b> {markets['spread']}\n"
            if markets["total"]:
                msg += f"<b>Тотал:</b> {markets['total']}\n"
                
            msg += f"\n👉 <i>Сравни с BetBoom!</i>"
            
            send_telegram_message(msg)
            sent_set.add(match_id)
            matches_found += 1
            
    if matches_found > 0:
        print(f"Отправлено: {matches_found}")
        save_sent(sent_set)

if __name__ == "__main__":
    print("Бот запущен (исходы + тоталы + форы)...")
    sent_set = load_sent()
    
    start_time = time.time()
    lt_cache = {}
    last_lt_update = 0
    
    while time.time() - start_time < 19800:
        now_msk = datetime.now(timezone.utc) + timedelta(hours=3)
        current_hour = now_msk.hour
        
        if 0 <= current_hour < 8:
            print(f"Ночь ({now_msk.strftime('%H:%M')} МСК). Сплю 1 час...")
            time.sleep(3600) 
            continue
        
        current_time = time.time()
        
        if current_time - last_lt_update > 1800:
            print(f"[{now_msk.strftime('%H:%M')}] Обновляю Live Tennis...")
            lt_cache = get_livetennis_times()
            last_lt_update = current_time
            
        print(f"[{now_msk.strftime('%H:%M')}] Проверяю Pinnacle...")
        check_upcoming_matches(sent_set, lt_cache)
        
        time.sleep(600) # Спим 10 минут
        
    print("Цикл завершен.")
