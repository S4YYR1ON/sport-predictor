import requests
import streamlit as st
from datetime import datetime

TIMEOUT = 10

# ========== ESPN (резерв) ==========
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"
ESPN_PATHS = {
    "football": [("soccer/eng.1", "Английская Премьер-лига"), ("soccer/uefa.champions", "Лига чемпионов")],
    "tennis": [("tennis/atp", "ATP Tennis")]
}

# ========== API-Sports ==========
API_SPORTS_BASE = {
    "football": "https://v3.football.api-sports.io",
    "basketball": "https://v1.basketball.api-sports.io",
    "hockey": "https://v1.hockey.api-sports.io",
    "mma": "https://v1.mma.api-sports.io"
}
API_SPORTS_ENDPOINTS = {
    "football": "/fixtures",
    "basketball": "/games",
    "hockey": "/games",
    "mma": "/fights"
}

# ========== Live Tennis API ==========
LIVETENNIS_BASE = "https://api.livetennisapi.com/v1"

@st.cache_data(ttl=600)
def get_tennis_events():
    """Получает предстоящие теннисные матчи из Live Tennis API."""
    try:
        api_key = st.secrets["LIVETENNIS_API_KEY"]
    except (KeyError, FileNotFoundError):
        return None, "Ключ Live Tennis API не настроен."

    url = "https://api.livetennisapi.com/api/public/v1/matches"
    # Используем заголовок X-API-Key, как указано в документации
    headers = {"X-API-Key": api_key}
    params = {"status": "upcoming"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, list):
            matches_list = data
        elif isinstance(data, dict):
            matches_list = data.get("matches") or data.get("data") or []
        else:
            matches_list = []

        if not matches_list:
            return [], "Ответ получен, но матчи не найдены."

        events = []
        for match in matches_list:
            if not isinstance(match, dict):
                continue

            players = match.get("players") or {}
            p1 = players.get("p1") or {}
            p2 = players.get("p2") or {}

            home = p1.get("name")
            away = p2.get("name")

            if not home or not away:
                continue

            draw = match.get("draw", "")
            status = match.get("event_status") or "scheduled"
            has_market = match.get("has_market", False)
            match_id = match.get("id")

            if status == "Finished":
                continue

            start = match.get("created_at") or ""
            draw_label = "Одиночный" if draw == "singles" else "Парный"
            market_label = "коэф. есть" if has_market else "коэф. нет"

            events.append({
                "home": home,
                "away": away,
                "start": start,
                "source": f"Live Tennis API · {draw_label} · {market_label}",
                "odds_home": None,
                "odds_away": None,
                "match_id": match_id,
                "has_market": has_market
            })

        if not events:
            return [], "Матчи получены, но подходящих не найдено."

        return events, f"Источник: Live Tennis API. Найдено матчей: {len(events)}."
    except Exception as e:
        return None, f"Ошибка Live Tennis API: {type(e).__name__} - {e}"

@st.cache_data(ttl=600)
def get_match_odds(match_id):
    """Получает коэффициенты для конкретного матча по его ID."""
    try:
        api_key = st.secrets["LIVETENNIS_API_KEY"]
    except (KeyError, FileNotFoundError):
        return None, "Ключ не настроен."

    # Новый эндпоинт из документации
    url = "https://api.livetennisapi.com/api/public/v1/markets"
    headers = {"X-API-Key": api_key}
    params = {"match_id": match_id}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        
        # Если PRO-тариф требуется, вернём понятную ошибку
        if response.status_code in [401, 403]:
            return None, "Для получения коэффициентов нужен тариф PRO."
            
        response.raise_for_status()
        data = response.json()

        # Согласно документации, data содержит максимум один объект
        markets = data.get("data", [])
        if not markets:
            return None, "Коэффициенты для этого матча не найдены."

        market = markets[0]
        
        # Пытаемся извлечь коэффициенты (структура может отличаться)
        # Обычно это home_odds / away_odds или p1_odds / p2_odds
        home_odd = market.get("home_odds") or market.get("p1_odds") or market.get("home")
        away_odd = market.get("away_odds") or market.get("p2_odds") or market.get("away")

        if not home_odd or not away_odd:
            return None, "Не удалось распознать структуру коэффициентов."

        return {"home": home_odd, "away": away_odd}, None
    except Exception as e:
        return None, f"Ошибка: {type(e).__name__} - {e}"

@st.cache_data(ttl=600)
def get_api_sports_events(sport, date_str=None):
    """Получает матчи из API-Sports для футбола, баскетбола, хоккея, ММА."""
    try:
        api_key = st.secrets["API_SPORTS_KEY"]
    except (KeyError, FileNotFoundError):
        return None, "Ключ API-Sports не настроен."

    base_url = API_SPORTS_BASE.get(sport)
    endpoint = API_SPORTS_ENDPOINTS.get(sport)
    if not base_url or not endpoint:
        return None, f"API-Sports не поддерживает вид спорта: {sport}"

    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    url = f"{base_url}{endpoint}"
    headers = {"x-apisports-key": api_key}
    params = {"date": date_str}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        events = []
        for item in data.get("response", []):
            home, away = None, None
            if sport == "football":
                teams = item.get("teams", {})
                home = teams.get("home", {}).get("name")
                away = teams.get("away", {}).get("name")
            elif sport in ["basketball", "hockey"]:
                teams = item.get("teams", {})
                home = teams.get("home", {}).get("name")
                away = teams.get("away", {}).get("name")
            elif sport == "mma":
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
    # Теннис — Live Tennis API
    if sport == "tennis":
        events, error = get_tennis_events()
        if events:
            return events, "Источник: Live Tennis API."
        else:
            # Резерв: ESPN
            st.warning(f"Live Tennis API недоступен: {error}. Использую ESPN.")
            return get_espn_events(sport)

    # Футбол, баскетбол, хоккей, ММА — API-Sports
    if sport in ["football", "basketball", "hockey", "mma"]:
        events, error = get_api_sports_events(sport)
        if events:
            return events, f"Источник: API-Sports. Коэффициенты вводи вручную."
        else:
            # Резерв: ESPN для футбола
            if sport == "football":
                st.warning(f"API-Sports недоступен: {error}. Использую ESPN.")
                return get_espn_events(sport)
            return [], f"API-Sports недоступен: {error}"

    # Dota 2, CS2
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

def get_espn_events(sport):
    """Резервный источник ESPN."""
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
    warning = ("Часть источников недоступна: " + "; ".join(errors)) if errors else "Источник: ESPN."
    return events, warning

def source_status():
    out = {}
    # API-Sports
    try:
        api_key = st.secrets["API_SPORTS_KEY"]
        headers = {"x-apisports-key": api_key}
        r = requests.get("https://v3.football.api-sports.io/status", headers=headers, timeout=TIMEOUT)
        out["API-Sports"] = "OK" if r.ok else f"HTTP {r.status_code}"
    except Exception as e:
        out["API-Sports"] = f"ошибка ({type(e).__name__})"

    # Live Tennis API
    try:
        api_key = st.secrets["LIVETENNIS_API_KEY"]
        headers = {"Authorization": f"Bearer {api_key}"}
        r = requests.get(f"{LIVETENNIS_BASE}/status", headers=headers, timeout=TIMEOUT)
        out["Live Tennis API"] = "OK" if r.ok else f"HTTP {r.status_code}"
    except Exception as e:
        out["Live Tennis API"] = f"ошибка ({type(e).__name__})"

    out["ESPN"] = "Резервный источник"
    out["CS2 расписание"] = "не подключено"
    out["BetBoom"] = "не подключён"
    return out
