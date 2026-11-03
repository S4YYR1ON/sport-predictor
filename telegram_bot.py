import os
import json
import requests
import time
import threading
from datetime import datetime, timezone, timedelta
import telebot
from telebot import types
from livetennisapi import LiveTennisAPI

# ==========================================
# НАСТРОЙКИ
# ==========================================
TG_TOKEN = os.getenv("TG_TOKEN")
PINNAPI_KEY = os.getenv("PINNAPI_API_KEY")
LIVETENNIS_KEY = os.getenv("LIVETENNIS_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")

THREAD_ID_NOTIFICATIONS = int(os.getenv("THREAD_ID_NOTIFICATIONS", 0))
THREAD_ID_MY_BETS = int(os.getenv("THREAD_ID_MY_BETS", 0))
THREAD_ID_STATS = int(os.getenv("THREAD_ID_STATS", 0))

bot = telebot.TeleBot(TG_TOKEN)
SENT_FILE = "sent_matches.json"

# ==========================================
# ФИЛЬТР ТОПОВЫХ ЛИГ
# ==========================================
def is_top_tournament(league_name):
    """Проверяет, является ли турнир топовым (ATP/WTA), а не ITF/Challenger"""
    if not league_name:
        return False
    name_lower = str(league_name).lower()
    
    # Исключаем низшие лиги
    exclude = [
        "itf", "challenger", "w15", "w25", "w35", "w50", "w75", "w100",
        "m15", "m25", "wta 125", "atp 125", "125k", "utr", "doubles"
    ]
    if any(word in name_lower for word in exclude):
        return False
        
    # Оставляем только ATP или WTA
    return "atp" in name_lower or "wta" in name_lower

# ==========================================
# РАБОТА С SUPABASE
# ==========================================
def supabase_request(method, endpoint, data=None):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = {
        "apikey": SUPABASE_KEY, 
        "Authorization": f"Bearer {SUPABASE_KEY}", 
        "Content-Type": "application/json", 
        "Prefer": "return=representation"
    }
    if method == "POST": 
        r = requests.post(url, headers=headers, json=data)
    elif method == "PATCH": 
        r = requests.patch(url, headers=headers, json=data)
    else: 
        r = requests.get(url, headers=headers)
    return r.json()

def load_sent():
    if os.path.exists(SENT_FILE):
        try:
            with open(SENT_FILE, "r") as f: return set(json.load(f))
        except: return set()
    return set()

def save_sent(sent_set):
    with open(SENT_FILE, "w") as f: json.dump(list(sent_set), f)

# ==========================================
# ВРЕМЯ ИЗ LIVE TENNIS API
# ==========================================
def get_livetennis_times():
    times = {}
    if not LIVETENNIS_KEY: 
        print("❌ ОШИБКА: LIVETENNIS_KEY не задан в секретах!")
        return times
    try:
        print("📡 Запрашиваю Live Tennis API...")
        with LiveTennisAPI(api_key=LIVETENNIS_KEY) as client:
            fixtures = client.list_fixtures(limit=200)
            print(f"📡 Live Tennis вернул матчей: {len(fixtures)}")
            
            for idx, match in enumerate(fixtures):
                tour = str(getattr(match, 'tour', '')).lower()
                if tour not in ['atp', 'wta']: continue
                
                p1 = str(getattr(match, 'player1_name', '')).lower().strip()
                p2 = str(getattr(match, 'player2_name', '')).lower().strip()
                
                # Диагностика первого попавшегося матча
                if idx == 0:
                    print(f"🔍 Пример из Live Tennis: {p1} vs {p2} | Время: {getattr(match, 'start_time', None)}")
                
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
        print(f"❌ Ошибка LiveTennis: {e}")
    return times

# ==========================================
# ФОНОВЫЙ ПОТОК (УВЕДОМЛЕНИЯ)
# ==========================================
def check_upcoming_matches():
    print("=== НАЧАЛО ПРОВЕРКИ МАТЧЕЙ ===")
    if not PINNAPI_KEY: return
    now_utc = datetime.now(timezone.utc)
    sent_set = load_sent()
    
    lt_times = get_livetennis_times()
    print(f"🕒 Временных меток от Live Tennis: {len(lt_times)}")

    url = "https://pinnapi.com/kit/v1/prematch/fixtures"
    try:
        r = requests.get(url, headers={"x-portal-apikey": PINNAPI_KEY}, params={"sport_id": 2}, timeout=15)
        if r.status_code != 200: return
        events_list = r.json().get("events", [])
        print(f"📊 Получено событий от Pinnapi: {len(events_list)}")
    except Exception as e: 
        print(f"❌ Ошибка API Pinnapi: {e}")
        return

    debug_count = 0
    for ev in events_list:
        home = str(ev.get("home", "")).strip()
        away = str(ev.get("away", "")).strip()
        if not home or not away or "(Games)" in home or "/" in home: continue

        # 1. Фильтр топ-лиг
        league_name = ev.get("league_name") or ev.get("league") or ev.get("tournament")
        if isinstance(league_name, dict):
            league_name = league_name.get("name", "")
            
        if not is_top_tournament(league_name):
            continue

        match_time = None

        # 2. Пытаемся найти в Live Tennis
        h_parts = home.lower().split()
        a_parts = away.lower().split()
        if h_parts and a_parts:
            h_last = h_parts[-1]
            a_last = a_parts[-1]
            match_time = lt_times.get(f"{h_last}_{a_last}") or lt_times.get(f"{a_last}_{h_last}")

        # 3. Если нет в Live Tennis, берем из Pinnapi (поле 'starts')
        if not match_time:
            start_ts = ev.get("start") or ev.get("starts")
            if start_ts:
                try:
                    match_time = datetime.fromisoformat(str(start_ts).split(".")[0].replace("Z", "")).replace(tzinfo=timezone.utc)
                except: 
                    pass

        if not match_time:
            continue

        time_left = (match_time - now_utc).total_seconds() / 60.0
        match_id = ev.get("event_id") or ev.get("id")

        # --- ОТЛАДКА (показываем первые 5 валидных матчей) ---
        if debug_count < 5:
            print(f"🔍 Матч: {home} - {away} | Лига: {league_name} | Через {time_left:.1f} мин")
            debug_count += 1
        # ----------------------------------------------------

        # ТЕСТОВОЕ ОКНО 60 МИНУТ (потом поменяем на 15)
        if 0 < time_left <= 15 and match_id not in sent_set:
            periods = ev.get("periods", {})
            main = periods.get("num_0", {})
            ml = main.get("money_line", {})
            
            if not ml or not ml.get("home"): continue
            o_h, o_a = ml.get("home"), ml.get("away")
            
            msg = f"🚨 <b>Матч через {int(time_left)} мин!</b> 🚨\n"
            msg += f"🏆 <b>{home}</b> — <b>{away}</b>\n\n"
            msg += f"<b>Исход:</b> {o_h:.2f} / {o_a:.2f}\n"
            
            totals = main.get("totals", {})
            if totals:
                best_line = list(totals.keys())[0]
                t_data = totals[best_line]
                msg += f"<b>Тотал (сет):</b>\nТМ({best_line}): {t_data.get('under', 0):.2f} | ТБ({best_line}): {t_data.get('over', 0):.2f}\n"
            
            spreads = main.get("spreads", {})
            if spreads:
                best_line = list(spreads.keys())[0]
                s_data = spreads[best_line]
                msg += f"<b>Фора (сет):</b>\nФ1({s_data.get('hdp')}): {s_data.get('home', 0):.2f} | Ф2({-float(s_data.get('hdp'))}): {s_data.get('away', 0):.2f}\n"
            
            msg += f"\n👉 <i>Ответь на это сообщение, чтобы сохранить ставку!</i>"
            
            try:
                t_id = THREAD_ID_NOTIFICATIONS if THREAD_ID_NOTIFICATIONS > 1 else None
                bot.send_message(GROUP_CHAT_ID, msg, parse_mode="HTML", message_thread_id=t_id)
                print(f"✅ ОТПРАВЛЕНО: {home} - {away}")
                sent_set.add(match_id)
                save_sent(sent_set)
            except Exception as e:
                print(f"❌ ОШИБКА ОТПРАВКИ: {e}")

def background_worker():
    while True:
        now_msk = datetime.now(timezone.utc) + timedelta(hours=3)
        if 8 <= now_msk.hour < 24: # Работаем днем
            check_upcoming_matches()
        time.sleep(600) # Спим 10 минут

# ==========================================
# ОБРАБОТКА ОТВЕТОВ (СОЗДАНИЕ СТАВКИ)
# ==========================================
@bot.message_handler(func=lambda message: message.reply_to_message is not None and str(message.chat.id) == str(GROUP_CHAT_ID))
def handle_bet_reply(message):
    original_msg = message.reply_to_message.text
    user_text = message.text.upper().replace(",", " ").replace(".", ",").split()
    
    try:
        ml_str = original_msg.split("Исход:")[1].split("\n")[0].strip()
        pin_ml = [float(x.strip()) for x in ml_str.split("/")]
        tot_str = original_msg.split("ТМ(")[1].split("\n")[0]
        pin_tm = float(tot_str.split("): ")[1].split(" |")[0])
        pin_tb = float(tot_str.split("ТБ(")[1].split("): ")[1])
        sp_str = original_msg.split("Ф1(")[1].split("\n")[0]
        pin_f1 = float(sp_str.split("): ")[1].split(" |")[0])
        pin_f2 = float(sp_str.split("Ф2(")[1].split("): ")[1])
    except:
        bot.reply_to(message, "❌ Не смог прочитать кэфы Pinnacle из сообщения.")
        return

    bets_to_save = []
    i = 0
    while i < len(user_text):
        market = user_text[i]
        if market in ["ТБ", "ТМ", "П1", "П2", "Ф1", "Ф2"] and i + 1 < len(user_text):
            try:
                user_odd = float(user_text[i+1].replace(",", "."))
                pin_odd = None
                if market == "ТБ": pin_odd = pin_tb
                elif market == "ТМ": pin_odd = pin_tm
                elif market == "П1": pin_odd = pin_ml[0]
                elif market == "П2": pin_odd = pin_ml[1]
                elif market == "Ф1": pin_odd = pin_f1
                elif market == "Ф2": pin_odd = pin_f2
                
                if pin_odd:
                    clv = (user_odd / pin_odd) - 1
                    bets_to_save.append((market, user_odd, pin_odd, clv))
            except: pass
            i += 2
        else: i += 1

    if not bets_to_save:
        bot.reply_to(message, "❌ Не распознал ставки. Пиши строго: ТБ 2.7, Ф1 2.5")
        return

    match_name = original_msg.split("\n")[1].replace("<b>", "").replace("</b>", "")
    
    for market, u_odd, p_odd, clv in bets_to_save:
        data = {
            "chat_id": message.chat.id, 
            "user_id": message.from_user.id,
            "username": message.from_user.username or message.from_user.first_name,
            "match_name": match_name, 
            "market": market, 
            "user_odds": u_odd, 
            "pinnacle_odds": p_odd, 
            "clv": clv
        }
        res = supabase_request("POST", "telegram_bets", data)
        
        if res:
            bet_id = res[0]["id"]
            card_text = f"📝 <b>Ставка: {match_name}</b>\nРынок: <b>{market}</b>\nТвой кэф: <b>{u_odd}</b> (Pinnacle: {p_odd:.2f})\nCLV: <b>{clv:+.2%}</b>\n\n<i>Выбери результат:</i>"
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("✅ Выиграл", callback_data=f"win_{bet_id}"), 
                types.InlineKeyboardButton("❌ Проиграл", callback_data=f"lose_{bet_id}"), 
                types.InlineKeyboardButton("🔄 Возврат", callback_data=f"void_{bet_id}")
            )
            b_id = THREAD_ID_MY_BETS if THREAD_ID_MY_BETS > 1 else None
            bot.send_message(GROUP_CHAT_ID, card_text, reply_markup=markup, parse_mode="HTML", message_thread_id=b_id)
    
    bot.reply_to(message, "✅ Ставки сохранены!")

# ==========================================
# ОБРАБОТКА КНОПОК
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    action, bet_id = call.data.split("_")
    status_map = {"win": "won", "lose": "lost", "void": "void"}
    status_ru = {"won": "✅ Выигрыш", "lost": "❌ Проигрыш", "void": "🔄 Возврат"}
    new_status = status_map[action]
    
    supabase_request("PATCH", f"telegram_bets?id=eq.{bet_id}", {"status": new_status})
    
    new_text = call.message.text + f"\n\n<b>Статус: {status_ru[new_status]}</b>"
    bot.edit_message_text(new_text, call.message.chat.id, call.message.message_id, parse_mode="HTML")
    bot.answer_callback_query(call.id, "Ставка закрыта!")

# ==========================================
# СТАТИСТИКА
# ==========================================
@bot.message_handler(commands=['stats'])
def show_stats(message):
    user_id = message.from_user.id
    res = supabase_request("GET", f"telegram_bets?user_id=eq.{user_id}&status=neq.open", None)
    
    if not res:
        s_id = THREAD_ID_STATS if THREAD_ID_STATS > 1 else None
        bot.send_message(GROUP_CHAT_ID, f"📊 {message.from_user.first_name}, у тебя пока нет закрытых ставок.", message_thread_id=s_id)
        return
        
    total = len(res)
    won = sum(1 for r in res if r["status"] == "won")
    lost = sum(1 for r in res if r["status"] == "lost")
    void = sum(1 for r in res if r["status"] == "void")
    avg_clv = sum(r["clv"] for r in res) / total if total > 0 else 0
    profit = (won * 1.0) - (lost * 1.0)
    
    text = f"📊 <b>Статистика: {message.from_user.first_name}</b>\n\n<pre>"
    text += f"Всего ставок:  {total}\n✅ Побед:       {won}\n❌ Поражений:   {lost}\n🔄 Возвратов:   {void}\n------------------------\n📈 Средний CLV: {avg_clv:+.2%}\n💰 Профит (ед.): {profit:+.1f}</pre>"
    
    s_id = THREAD_ID_STATS if THREAD_ID_STATS > 1 else None
    bot.send_message(GROUP_CHAT_ID, text, parse_mode="HTML", message_thread_id=s_id)

# ==========================================
# ЗАПУСК
# ==========================================
if __name__ == "__main__":
    try:
        print("📤 Отправляю тест...")
        t_id = THREAD_ID_NOTIFICATIONS if THREAD_ID_NOTIFICATIONS > 1 else None
        bot.send_message(GROUP_CHAT_ID, "🛠️ <b>Бот перезапущен с фильтром топ-лиг!</b>", parse_mode="HTML", message_thread_id=t_id)
    except Exception as e:
        print(f"❌ ОШИБКА ТЕСТА: {e}")

    threading.Thread(target=background_worker, daemon=True).start()
    print("Бот запущен в режиме 24/7...")
    bot.infinity_polling(timeout=30)
