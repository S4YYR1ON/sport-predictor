import os
import json
import requests
import time
import threading
from datetime import datetime, timezone, timedelta
import telebot
from telebot import types

# ==========================================
# НАСТРОЙКИ (Берутся из GitHub Secrets)
# ==========================================
TG_TOKEN = os.getenv("TG_TOKEN")
PINNAPI_KEY = os.getenv("PINNAPI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")

# ID тем в Telegram
THREAD_ID_NOTIFICATIONS = int(os.getenv("THREAD_ID_NOTIFICATIONS", 0))
THREAD_ID_MY_BETS = int(os.getenv("THREAD_ID_MY_BETS", 0))
THREAD_ID_STATS = int(os.getenv("THREAD_ID_STATS", 0))

bot = telebot.TeleBot(TG_TOKEN)
SENT_FILE = "sent_matches.json"

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

# ==========================================
# ФОНОВЫЙ ПОТОК (УВЕДОМЛЕНИЯ О МАТЧАХ)
# ==========================================
def check_upcoming_matches():
    print("=== ЖЕСТКИЙ ТЕСТ ОТПРАВКИ ===")
    if not PINNAPI_KEY: return

    url = "https://pinnapi.com/kit/v1/prematch/fixtures"
    try:
        r = requests.get(url, headers={"x-portal-apikey": PINNAPI_KEY}, params={"sport_id": 2}, timeout=15)
        events_list = r.json().get("events", [])
        print(f"📊 Получено событий: {len(events_list)}")
    except Exception as e: 
        print(f"Ошибка API: {e}")
        return

    if events_list:
        ev = events_list[0] # Берем ПЕРВЫЙ попавшийся матч
        home = str(ev.get("home", "")).strip()
        away = str(ev.get("away", "")).strip()
        
        msg = f"🧪 <b>ТЕСТ!</b>\n🏆 <b>{home}</b> — <b>{away}</b>\n\nОтветь на это сообщение: <code>ТБ 2.7</code>"
        
        try:
            t_id = THREAD_ID_NOTIFICATIONS if THREAD_ID_NOTIFICATIONS > 1 else None
            bot.send_message(GROUP_CHAT_ID, msg, parse_mode="HTML", message_thread_id=t_id)
            print(f"✅ ТЕСТОВОЕ УВЕДОМЛЕНИЕ ОТПРАВЛЕНО ДЛЯ: {home} - {away}")
        except Exception as e:
            print(f"❌ ОШИБКА ОТПРАВКИ: {e}")

def background_worker():
    while True:
        now_msk = datetime.now(timezone.utc) + timedelta(hours=3)
        if 8 <= now_msk.hour < 24:
            check_upcoming_matches()
        time.sleep(600)

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
            # ФИКС GENERAL ТЕМЫ
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
    # --- ТЕСТ ОТПРАВКИ ---
    try:
        print("📤 Пытаюсь отправить тестовое сообщение в группу...")
        t_id = THREAD_ID_NOTIFICATIONS if THREAD_ID_NOTIFICATIONS > 1 else None
        bot.send_message(
            GROUP_CHAT_ID, 
            "🛠️ <b>Тестовое сообщение от бота!</b>\nЕсли ты это видишь, значит группа и темы настроены верно.", 
            parse_mode="HTML",
            message_thread_id=t_id
        )
        print("✅ Тестовое сообщение успешно отправлено!")
    except Exception as e:
        print(f"❌ ОШИБКА ОТПРАВКИ ТЕСТА: {e}")

    threading.Thread(target=background_worker, daemon=True).start()
    print("Бот запущен в режиме 24/7 (Long Polling)...")
    bot.infinity_polling(timeout=30)
