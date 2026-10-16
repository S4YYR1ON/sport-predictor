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
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"status": "upcoming"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()

        # Определяем, где находится список матчей
        if isinstance(data, list):
            matches_list = data
        elif isinstance(data, dict):
            matches_list = data.get("matches") or data.get("data") or []
            if isinstance(matches_list, dict):
                matches_list = matches_list.get("matches", [])
        else:
            matches_list = []

        if not matches_list:
            return [], f"Ответ получен, но матчи не найдены. Первые 500 символов: {str(data)[:500]}"

        events = []
        for match in matches_list:
            if not isinstance(match, dict):
                continue

            # Извлекаем имена игроков, пробуя разные варианты
            def extract_name(obj):
                if isinstance(obj, dict):
                    return obj.get("name") or obj.get("player") or obj.get("full_name")
                return str(obj) if obj else None

            home = (
                extract_name(match.get("player1")) or
                extract_name(match.get("home_player")) or
                extract_name(match.get("player_home")) or
                extract_name(match.get("home")) or
                extract_name(match.get("player1_name"))
            )
            away = (
                extract_name(match.get("player2")) or
                extract_name(match.get("away_player")) or
                extract_name(match.get("player_away")) or
                extract_name(match.get("away")) or
                extract_name(match.get("player2_name"))
            )

            if not home or not away:
                # Показываем структуру одного матча для отладки
                st.warning(f"⚠️ Не удалось распознать имена. Структура матча: {str(match)[:600]}")
                continue

            events.append({
                "home": home,
                "away": away,
                "start": match.get("start_time") or match.get("date") or match.get("start") or "",
                "source": "Live Tennis API",
                "odds_home": None,
                "odds_away": None
            })

        if not events:
            return [], "Матчи получены, но имена игроков не распознаны. Смотри предупреждение выше."

        return events, "Источник: Live Tennis API."
    except Exception as e:
        return None, f"Ошибка Live Tennis API: {type(e).__name__} - {e}"

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
