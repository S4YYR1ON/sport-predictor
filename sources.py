import requests
import streamlit as st
from datetime import datetime

TIMEOUT = 10
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"

# ESPN только для тенниса и футбола
ESPN_PATHS = {
    "football": [("soccer/eng.1", "Английская Премьер-лига"), ("soccer/uefa.champions", "Лига чемпионов")],
    "tennis": [("tennis/atp", "ATP Tennis")]
}

# API-Sports для баскетбола, хоккея, ММА
API_SPORTS_BASE = {
    "basketball": "https://v1.basketball.api-sports.io",
    "hockey": "https://v1.hockey.api-sports.io",
    "mma": "https://v1.mma.api-sports.io"
}

@st.cache_data(ttl=600)  # кэш на 10 минут
def get_api_sports_events(sport, date_str=None):
    """Получает матчи из API-Sports для баскетбола, хоккея, ММА."""
    try:
        api_key = st.secrets["API_SPORTS_KEY"]
    except (KeyError, FileNotFoundError):
        return None, "Ключ API-Sports не настроен."

    base_url = API_SPORTS_BASE.get(sport)
    if not base_url:
        return None, f"API-Sports не поддерживает вид спорта: {sport}"

    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    url = f"{base_url}/games"
    headers = {"x-apisports-key": api_key}
    params = {"date": date_str}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        events = []
        for item in data.get("response", []):
            # Пытаемся извлечь названия команд/участников
            home = None
            away = None
            if "teams" in item:
                home = item["teams"].get("home", {}).get("name")
                away = item["teams"].get("away", {}).get("name")
            elif "fighters" in item:
                # Для ММА
                fighters = item.get("fighters", {})
                home = fighters.get("first", {}).get("name")
                away = fighters.get("second", {}).get("name")
            
            if home and away:
                events.append({
                    "home": home,
                    "away": away,
                    "start": item.get("date", ""),
                    "source": f"API-Sports · {sport}",
                    "odds_home": None,
                    "odds_away": None
                })
        return events, None
    except Exception as e:
        return None, f"Ошибка API-Sports: {type(e).__name__}"

def get_events(sport):
    # Теннис и футбол — ESPN
    if sport in ["football", "tennis"]:
        events = []
        errors = []
        for path, label in ESPN_PATHS.get(sport, []):
            try:
                r = requests.get(f"{ESPN_BASE}/{path}/scoreboard", timeout=TIMEOUT,
                                 headers={"User-Agent": "SportPredictorMVP/1.0"})
                r.raise_for_status()
                for ev in r.json().get("events", []):
                    comps = ev.get("competitions", [])
                    competitors = comps[0].get("competitors", []) if comps else []
                    if len(competitors) < 2:
                        continue
                    home = next((x for x in competitors if x.get("homeAway") == "home"), competitors[0])
                    away = next((x for x in competitors if x.get("homeAway") == "away"), competitors[1])
                    events.append({
                        "home": home.get("team", {}).get("displayName", "Unknown"),
                        "away": away.get("team", {}).get("displayName", "Unknown"),
                        "start": ev.get("date", ""),
                        "source": f"ESPN · {label}",
                        "odds_home": None,
                        "odds_away": None
                    })
            except Exception as e:
                errors.append(f"{label}: {type(e).__name__}")
        warning = ("Часть источников недоступна: " + "; ".join(errors)) if errors else "Источник: ESPN. Расписание может быть неполным."
        return events, warning

    # Баскетбол, хоккей, ММА — API-Sports
    if sport in ["basketball", "hockey", "mma"]:
        events, error = get_api_sports_events(sport)
        if events:
            return events, f"Источник: API-Sports. Коэффициенты не подключены, вводи вручную."
        else:
            return [], f"API-Sports недоступен: {error}"

    # Остальные виды спорта (Dota 2, CS2)
    if sport == "dota2":
        try:
            r = requests.get("https://api.opendota.com/api/status", timeout=TIMEOUT)
            r.raise_for_status()
            return [], "OpenDota доступен, но не даёт расписания будущих матчей."
        except Exception as e:
            return [], f"OpenDota временно недоступен: {type(e).__name__}"
    if sport == "cs2":
        return [], "Источник CS2 не подключён."

    return [], "Нет доступных матчей."

def source_status():
    out = {}
    # Проверяем ESPN
    for name, url in [
        ("ESPN NBA", "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"),
        ("OpenDota", "https://api.opendota.com/api/status")
    ]:
        try:
            r = requests.get(url, timeout=TIMEOUT)
            out[name] = "OK" if r.ok else f"HTTP {r.status_code}"
        except Exception as e:
            out[name] = f"ошибка ({type(e).__name__})"

    # Проверяем API-Sports
    try:
        api_key = st.secrets["API_SPORTS_KEY"]
        headers = {"x-apisports-key": api_key}
        r = requests.get("https://v1.basketball.api-sports.io/status", headers=headers, timeout=TIMEOUT)
        out["API-Sports"] = "OK" if r.ok else f"HTTP {r.status_code}"
    except Exception as e:
        out["API-Sports"] = f"ошибка ({type(e).__name__})"

    out["CS2 расписание"] = "не подключено"
    out["BetBoom"] = "не подключён"
    return out
