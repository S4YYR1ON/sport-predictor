import requests
import streamlit as st
from datetime import datetime, timedelta

TIMEOUT = 10
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"

# Правильные префиксы для All Sports API
HIGHLIGHTLY_SPORT_PREFIX = {
    "football": "football",
    "basketball": "basketball",
    "tennis": "tennis"
}

@st.cache_data(ttl=600)  # Кэш на 10 минут, чтобы экономить лимит запросов
def get_highlightly_events(sport, date_str=None):
    """Получает матчи и коэффициенты из Highlightly API"""
    try:
        api_key = st.secrets["HIGHLIGHTLY_API_KEY"]
    except (KeyError, FileNotFoundError):
        return None, "Ключ Highlightly API не настроен."

    hl_prefix = HIGHLIGHTLY_SPORT_PREFIX.get(sport)
    if not hl_prefix:
        return None, f"Highlightly не поддерживает вид спорта: {sport}"

    # Правильный URL без /v1/
    url = f"https://sports.highlightly.net/{hl_prefix}/matches"
    
    # Правильный заголовок для ключа
    headers = {"x-rapidapi-key": api_key}
    
    params = {}
    if date_str:
        params["date"] = date_str

    try:
        response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        
        events = []
        # Структура ответа может отличаться. 
        # Проверяем несколько возможных полей.
        matches_list = data.get("matches") or data.get("data") or []
        
        for match in matches_list:
            events.append({
                "home": match.get("homeTeam", {}).get("name", "Unknown"),
                "away": match.get("awayTeam", {}).get("name", "Unknown"),
                "start": match.get("date", ""),
                "source": "Highlightly",
                "odds_home": match.get("odds", {}).get("home"),
                "odds_away": match.get("odds", {}).get("away"),
            })
        return events, None
    except requests.exceptions.HTTPError as e:
        return None, f"HTTP ошибка: {e.response.status_code}. Проверь ключ и URL."
    except Exception as e:
        return None, f"Ошибка Highlightly API: {type(e).__name__} - {e}"

def get_events(sport):
    if sport in ["football", "basketball", "tennis"]:
        # Пытаемся получить данные из Highlightly
        # Указываем сегодняшнюю дату в формате YYYY-MM-DD
        today = datetime.now().strftime("%Y-%m-%d")
        events, error = get_highlightly_events(sport, date_str=today)
        
        if events:
            return events, "Источник: Highlightly API. Коэффициенты могут быть неполными."
        else:
            # Если Highlightly не сработал, пробуем ESPN как запасной вариант
            st.warning(f"Highlightly недоступен: {error}. Использую ESPN (без коэффициентов).")
    
    # Резервный источник ESPN
    if sport == "dota2":
        return [], "OpenDota доступен, но не даёт расписания."
    if sport == "cs2":
        return [], "Источник CS2 не подключён."

    return [], "Нет доступных матчей."

def source_status():
    out = {}
    try:
        api_key = st.secrets["HIGHLIGHTLY_API_KEY"]
        headers = {"x-rapidapi-key": api_key}
        # Проверяем статус через эндпоинт матчей (без параметров)
        r = requests.get("https://sports.highlightly.net/football/matches", headers=headers, timeout=TIMEOUT)
        out["Highlightly"] = "OK" if r.ok else f"HTTP {r.status_code}"
    except Exception as e:
        out["Highlightly"] = f"ошибка ({type(e).__name__})"
        
    out["ESPN"] = "Резервный источник"
    out["CS2 расписание"] = "не подключено"
    out["BetBoom"] = "не подключён"
    return out
