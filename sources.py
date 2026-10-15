import requests
import streamlit as st
from datetime import datetime

TIMEOUT = 10
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"

# Маппинг видов спорта для Highlightly API
HIGHLIGHTLY_SPORT_MAP = {
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

    hl_sport = HIGHLIGHTLY_SPORT_MAP.get(sport)
    if not hl_sport:
        return None, f"Highlightly не поддерживает вид спорта: {sport}"

    # ВНИМАНИЕ: Проверь точный URL в документации Highlightly!
    # Обычно он выглядит так: 
    url = f"https://sports.highlightly.net/v1/{hl_sport}/matches"
    headers = {"x-api-key": api_key}
    params = {}
    if date_str:
        params["date"] = date_str

    try:
        response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        
        events = []
        # Предполагаемая структура ответа (проверь в документации!)
        for match in data.get("data", []):
            events.append({
                "home": match.get("homeTeam", {}).get("name", "Unknown"),
                "away": match.get("awayTeam", {}).get("name", "Unknown"),
                "start": match.get("date", ""),
                "source": "Highlightly",
                "odds_home": match.get("odds", {}).get("home"),
                "odds_away": match.get("odds", {}).get("away"),
            })
        return events, None
    except Exception as e:
        return None, f"Ошибка Highlightly API: {type(e).__name__}"

def get_events(sport):
    if sport in ["football", "basketball", "tennis"]:
        # Пытаемся получить данные из Highlightly
        events, error = get_highlightly_events(sport)
        if events:
            return events, "Источник: Highlightly API. Коэффициенты могут быть неполными."
        else:
            # Если Highlightly не сработал, пробуем ESPN как запасной вариант
            st.warning(f"Highlightly недоступен: {error}. Использую ESPN (без коэффициентов).")
    
    # Резервный источник ESPN (для dota2, cs2 или если Highlightly упал)
    if sport == "dota2":
        return [], "OpenDota доступен, но не даёт расписания."
    if sport == "cs2":
        return [], "Источник CS2 не подключён."

    return [], "Нет доступных матчей."

def source_status():
    out = {}
    try:
        api_key = st.secrets["HIGHLIGHTLY_API_KEY"]
        headers = {"x-api-key": api_key}
        r = requests.get("https://sports.highlightly.net/v1/status", headers=headers, timeout=TIMEOUT)
        out["Highlightly"] = "OK" if r.ok else f"HTTP {r.status_code}"
    except Exception as e:
        out["Highlightly"] = f"ошибка ({type(e).__name__})"
        
    out["ESPN"] = "Резервный источник"
    out["CS2 расписание"] = "не подключено"
    out["BetBoom"] = "не подключён"
    return out
