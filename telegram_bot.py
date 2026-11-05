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

bot = telebot.TeleBot(TG_TOKEN)
SENT_FILE = "sent_matches.json"

# ==========================================
# SUPABASE
# ==========================================
def supabase_request(method, endpoint, data=None):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = {
        "apikey": SUPABASE_KEY, 
        "Authorization": f"Bearer {SUPABASE_KEY}", 
        "Content-Type": "application/json", 
        "Prefer": "return=representation"
    }
    if method == "POST": r = requests.post(url, headers=headers, json=data)
    elif method == "PATCH": r = requests.patch(url, headers=headers, json=data)
    elif method == "DELETE": r = requests.delete(url, headers=headers)
    else: r = requests.get(url, headers=headers)
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
# КОМАНДА /setup ДЛЯ НАСТРОЙКИ ГРУППЫ
# ==========================================
@bot.message_handler(commands=['setup'])
def setup_group(message):
    if message.chat.type not in ['group', 'supergroup']:
        bot.reply_to(message, "❌ Эту команду нужно вызывать в группе!")
        return

    try:
        member = bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in ['creator', 'administrator']:
            bot.reply_to(message, "❌ Только создатель или админ группы может настроить бота.")
            return
    except:
        pass

    user_id = message.from_user.id
    chat_id = message.chat.id
    
    bot.reply_to(message, "⏳ Настраиваю группу. Это займет 5 секунд (создаю темы)...")

    try:
        # Создаем темы с паузами, чтобы Telegram не выдавал ошибку
        t_notif = bot.create_forum_topic(chat_id, "🔔 Уведомления").message_thread_id
        time.sleep(2) # Пауза 2 секунды
        
        t_bets = bot.create_forum_topic(chat_id, "📝 Мои ставки").message_thread_id
        time.sleep(2) # Пауза 2 секунды
        
        t_stats = bot.create_forum_topic(chat_id, "📊 Статистика").message_thread_id

        # Сохраняем в базу
        supabase_request("DELETE", f"user_settings?user_id=eq.{user_id}")
        data = {
            "user_id": user_id,
            "chat_id": chat_id,
            "thread_notif": t_notif,
            "thread_bets": t_bets,
            "thread_stats": t_stats
        }
        supabase_request("POST", "user_settings", data)
        
        bot.send_message(chat_id, "✅ <b>Группа успешно настроена!</b>\nВсе темы созданы.", parse_mode="HTML", message_thread_id=t_notif)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")
    # ... код создания тем (t_notif, t_bets, t_stats) ...

    # 1. Меняем название группы
    try:
        new_title = f"SportPredictorGroup"
        bot.set_chat_title(chat_id, new_title)
    except Exception as e:
        print(f"Не смог изменить название: {e}")

    # 2. Ставим аватарку группе
    try:
        image_url = "https://www.sostav.ru/blogs/images/feeds/123/245355.jpg"
            
        # Притворяемся браузером, чтобы сайт не блокировал скачивание
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        img_data = requests.get(image_url, headers=headers, timeout=10).content
            
        # Проверяем, что скачалось хоть что-то (а не пустая страница с ошибкой)
        if len(img_data) > 1000:
            bot.set_chat_photo(chat_id, photo=img_data)
            print("✅ Аватарка успешно изменена!")
        else:
            print("❌ Ошибка: Скачанный файл слишком маленький (возможно, сайт заблокировал).")
                
    except Exception as e:
        print(f"❌ Не смог изменить аватарку: {e}")
# ==========================================
# УВЕДОМЛЕНИЯ ДЛЯ ВСЕХ ПОЛЬЗОВАТЕЛЕЙ
# ==========================================
def check_upcoming_matches():
    print("=== ПРОВЕРКА МАТЧЕЙ ===")
    if not PINNAPI_KEY: return
    
    # Получаем список всех настроенных групп
    users = supabase_request("GET", "user_settings", None)
    if not users or isinstance(users, dict):
        print("Нет настроенных пользователей.")
        return

    now_utc = datetime.now(timezone.utc)
    sent_set = load_sent()
    
    # Получаем время из Live Tennis
    lt_times = {}
    if LIVETENNIS_KEY:
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
                    st = getattr(match, 'start_time', None)
                    if st and p1_last and p2_last:
                        clean_time = str(st).replace("Z", "+00:00")
                        dt = datetime.fromisoformat(clean_time)
                        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                        lt_times[f"{p1_last}_{p2_last}"] = dt
        except Exception as e:
            print(f"LiveTennis error: {e}")

    # Получаем кэфы из Pinnapi
    try:
        r = requests.get("https://pinnapi.com/kit/v1/prematch/fixtures", headers={"x-portal-apikey": PINNAPI_KEY}, params={"sport_id": 2}, timeout=15)
        if r.status_code != 200: return
        events_list = r.json().get("events", [])
    except: return

    for ev in events_list:
        home = str(ev.get("home", "")).strip()
        away = str(ev.get("away", "")).strip()
        if not home or not away or "(Games)" in home or "/" in home: continue

        league_name = ev.get("league_name") or ev.get("league") or ""
        if isinstance(league_name, dict): league_name = league_name.get("name", "")
        
        # Только ATP/WTA
        if not ("atp" in league_name.lower() or "wta" in league_name.lower()): continue
        if any(x in league_name.lower() for x in ["itf", "challenger", "m15", "w15", "w25", "w35", "w50", "w75", "w100"]): continue

        match_time = None
        h_parts = home.lower().split()
        a_parts = away.lower().split()
        if h_parts and a_parts:
            h_last = h_parts[-1]
            a_last = a_parts[-1]
            match_time = lt_times.get(f"{h_last}_{a_last}") or lt_times.get(f"{a_last}_{h_last}")

        if not match_time:
            start_ts = ev.get("start") or ev.get("starts")
            if start_ts:
                try:
                    match_time = datetime.fromisoformat(str(start_ts).split(".")[0].replace("Z", "")).replace(tzinfo=timezone.utc)
                except: pass
        if not match_time: continue

        time_left = (match_time - now_utc).total_seconds() / 60.0
        match_id = ev.get("event_id") or ev.get("id")

        if 0 < time_left <= 15 and match_id not in sent_set:
            periods = ev.get("periods", {})
            main = periods.get("num_0", {})
            ml = main.get("money_line", {})
            
            if not ml or not ml.get("home"): continue
            
            # Формируем сообщение
            msg = f"🚨 <b>Матч через {int(time_left)} мин!</b> 🚨\n"
            msg += f"🏆 <b>{home}</b> — <b>{away}</b>\n\n"
            msg += f"<b>Исход:</b> {ml.get('home'):.2f} / {ml.get('away'):.2f}\n"
            
            # Добавляем Тотал
            totals = main.get("totals", {})
            if totals:
                best_line = list(totals.keys())[0]
                t_data = totals[best_line]
                msg += f"<b>Тотал (сет):</b>\nТМ({best_line}): {t_data.get('under', 0):.2f} | ТБ({best_line}): {t_data.get('over', 0):.2f}\n"
            
            # Добавляем Фору
            spreads = main.get("spreads", {})
            if spreads:
                best_line = list(spreads.keys())[0]
                s_data = spreads[best_line]
                msg += f"<b>Фора (сет):</b>\nФ1({s_data.get('hdp')}): {s_data.get('home', 0):.2f} | Ф2({-float(s_data.get('hdp'))}): {s_data.get('away', 0):.2f}\n"
            
            msg += f"\n👉 <i>Ответь на это сообщение, чтобы сохранить ставку!</i>"
            
            # Отправляем КАЖДОМУ пользователю в его группу
            for user in users:
                try:
                    bot.send_message(user["chat_id"], msg, parse_mode="HTML", message_thread_id=user["thread_notif"])
                except Exception as e:
                    print(f"Ошибка отправки {user['user_id']}: {e}")
            
            sent_set.add(match_id)
            save_sent(sent_set)
            print(f"✅ Отправлено всем: {home} - {away}")

def background_worker():
    while True:
        now_msk = datetime.now(timezone.utc) + timedelta(hours=3)
        if 8 <= now_msk.hour < 24:
            check_upcoming_matches()
        time.sleep(600)

# ==========================================
# ОБРАБОТКА СТАВОК (ОТВЕТЫ)
# ==========================================
@bot.message_handler(func=lambda message: message.reply_to_message is not None and message.text and not message.text.startswith('/'))
def handle_bet_reply(message):
    original_msg = message.reply_to_message.text
    if not original_msg or "Матч через" not in original_msg:
        return
        
    user_text = message.text.upper().replace(",", " ").replace(".", ",").split()
    
    try:
        ml_str = original_msg.split("Исход:")[1].split("\n")[0].strip()
        pin_ml = [float(x.strip()) for x in ml_str.split("/")]
    except:
        bot.reply_to(message, "❌ Не смог прочитать кэфы Pinnacle из сообщения.")
        return

    bets_to_save = []
    i = 0
    while i < len(user_text):
        market = user_text[i]
        if market in ["П1", "П2"] and i + 1 < len(user_text):
            try:
                user_odd = float(user_text[i+1].replace(",", "."))
                pin_odd = pin_ml[0] if market == "П1" else pin_ml[1]
                clv = (user_odd / pin_odd) - 1
                bets_to_save.append((market, user_odd, pin_odd, clv))
            except: pass
            i += 2
        else: i += 1

    if not bets_to_save:
        bot.reply_to(message, "❌ Не распознал ставки. Пиши строго: П1 1.85 или П2 2.10")
        return

    match_name = original_msg.split("\n")[1].replace("<b>", "").replace("</b>", "")
    
    # Узнаем, в какую тему отправлять карточку
    settings = supabase_request("GET", f"user_settings?user_id=eq.{message.from_user.id}", None)
    if not settings or isinstance(settings, dict):
        bot.reply_to(message, "❌ Сначала настрой группу командой /setup")
        return
    t_bets = settings[0]["thread_bets"]

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
            bot.send_message(message.chat.id, card_text, reply_markup=markup, parse_mode="HTML", message_thread_id=t_bets)
    
    bot.reply_to(message, "✅ Ставки сохранены!")

# ==========================================
# КНОПКИ И СТАТИСТИКА
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    action, bet_id = call.data.split("_")
    res = supabase_request("GET", f"telegram_bets?id=eq.{bet_id}", None)
    if not res: return
    
    if str(call.from_user.id) != str(res[0]["user_id"]):
        bot.answer_callback_query(call.id, "⛔ Это не твоя ставка!", show_alert=True)
        return
        
    new_status = {"win": "won", "lose": "lost", "void": "void"}[action]
    supabase_request("PATCH", f"telegram_bets?id=eq.{bet_id}", {"status": new_status})
    
    status_ru = {"won": "✅ Выигрыш", "lost": "❌ Проигрыш", "void": "🔄 Возврат"}
    bot.edit_message_text(call.message.text + f"\n\n<b>Статус: {status_ru[new_status]}</b>", call.message.chat.id, call.message.message_id, parse_mode="HTML")
    bot.answer_callback_query(call.id, "Ставка закрыта!")

@bot.message_handler(commands=['stats'])
def show_stats(message):
    user_id = message.from_user.id
    settings = supabase_request("GET", f"user_settings?user_id=eq.{user_id}", None)
    t_stats = settings[0]["thread_stats"] if settings and not isinstance(settings, dict) else None

    res = supabase_request("GET", f"telegram_bets?user_id=eq.{user_id}&status=neq.open", None)
    if not res or isinstance(res, dict):
        bot.send_message(message.chat.id, "📊 У тебя пока нет ставок.", message_thread_id=t_stats)
        return
        
    total = len(res)
    won = sum(1 for r in res if r["status"] == "won")
    lost = sum(1 for r in res if r["status"] == "lost")
    profit = won - lost
    avg_clv = sum(r["clv"] for r in res) / total
    
    text = f"📊 <b>Твоя статистика</b>\n\n<pre>Всего: {total}\n✅ Побед: {won}\n❌ Поражений: {lost}\n📈 CLV: {avg_clv:+.2%}\n💰 Профит: {profit:+.1f}</pre>"
    bot.send_message(message.chat.id, text, parse_mode="HTML", message_thread_id=t_stats)

# ==========================================
# ЗАПУСК
# ==========================================
if __name__ == "__main__":
    threading.Thread(target=background_worker, daemon=True).start()
    
    last_update_id = None
    while True:
        try:
            updates = bot.get_updates(offset=last_update_id, timeout=20, limit=10)
            if updates:
                for update in updates:
                    last_update_id = update.update_id + 1
                    if update.message:
                        try:
                            if update.message.text == '/setup':
                                setup_group(update.message)
                            elif update.message.text == '/stats':
                                show_stats(update.message)
                            elif update.message.reply_to_message:
                                handle_bet_reply(update.message)
                        except Exception as e: print(f"Err: {e}")
                    elif update.callback_query:
                        try: handle_callback(update.callback_query)
                        except Exception as e: print(f"Btn Err: {e}")
        except Exception as e:
            time.sleep(5)
