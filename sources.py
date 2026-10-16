import requests
import streamlit as st
from datetime import datetime

TIMEOUT = 10

# ========== PinnWire (теннис + коэффициенты) ==========
PINNWIRE_BASE = "https://api.pinnwire.com/kit/v1"

@st.cache_data(ttl=600)
def get_pinnwire_tennis_odds():
    """Получает теннисные матчи и коэффициенты из PinnWire."""
    try:
        api_key = st.secrets["PINNWIRE_API_KEY"]
    except (KeyError, FileNotFoundError):
        return None, "Ключ PinnWire не настроен."

    url = f"{PINNWIRE_BASE}/markets"
    params = {"sport_id": 2, "key": api_key}  # sport_id=2 — теннис

    try:
        response = requests.get(url, params=params, timeout=TIMEOUT)
        if response.status_code in [401, 403]:
            return None, "PinnWire: неверный ключ или нет доступа."
        response.raise_for_status()
        data = response.json()

        # PinnWire может возвращать список в разных полях
        matches = data.get("events") or data.get("data") or data.get("markets") or []

        events = []
        for match in matches:
            if not isinstance(match, dict):
                continue
            home = match.get("home") or match.get("home_team") or match.get("player1")
            away = match.get("away") or match.get("away_team") or match.get("player2")
            odds = match.get("odds") or match.get("prices") or {}
            odds_home = odds.get("home") if isinstance(odds, dict) else None
            odds_away = odds.get("away") if isinstance(odds, dict) else None

            if home and away:
                events.append({
                    "home": home,
                    "away": away,
                    "start": match.get("start_time") or match.get("commence_time", ""),
                    "source": "PinnWire · Pinnacle",
                    "odds_home": odds_home,
                    "odds_away": odds_away,
                    "match_id": match.get("id"),
                })
        return events, None
    except Exception as e:
        return None, f"Ошибка PinnWire: {type(e).__name__} - {e}"

# ========== Live Tennis API (резерв без коэффициентов) ==========
LIVETENNIS_BASE = "https://api.livetennisapi.com/api/public/v1"

@st.cache_data(ttl=600)
def get_tennis_events_legacy():
    """Резервный источник: Live Tennis API (без коэффициентов)."""
    try:
        api_key = st.secrets["LIVETENNIS_API_KEY"]
    except (KeyError, FileNotFoundError):
        return [], "Ключ Live Tennis API не настроен."

    url = f"{LIVETENNIS_BASE}/matches"
    headers = {"X-API-Key": api_key}
    params = {"status": "upcoming"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()

        matches_list = data if isinstance(data, list) else data.get("matches") or data.get("data") or []
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
            status = match.get("event_status") or "scheduled"
            if status == "Finished":
                continue
            events.append({
                "home": home,
                "away": away,
                "start": match.get("created_at", ""),
                "source": "Live Tennis API · без коэф.",
                "odds_home": None,
                "odds_away": None,
                "match_id": match.get("id"),
            })
        return events, None
    except Exception as e:
        return [], f"Ошибка Live Tennis API: {type(e).__name__}"

# ========== ESPN (резерв для тенниса и футбола) ==========
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"
ESPN_PATHS = {
    "football": [("soccer/eng.1", "Английская Премьер-лига"), ("soccer/uefa.champions", "Лига чемпионов")],
    "tennis": [("tennis/atp", "ATP Tennis")]
}

def get_espn_events(sport):
    events, errors = [], []
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
                    "odds_away": None,
                })
        except Exception as e:
            errors.append(f"{label}: {type(e).__name__}")
    warning = ("Часть источников недоступна: " + "; ".join(errors)) if errors else "Источник: ESPN."
    return events, warning

# ========== Главная функция ==========
def get_events(sport):
    if sport == "tennis":
        # 1. PinnWire (с коэффициентами)
        events, error = get_pinnwire_tennis_odds()
        if events:
            return events, f"Источник: PinnWire (Pinnacle). Найдено матчей: {len(events)}."
        st.warning(f"PinnWire недоступен: {error}. Пробую Live Tennis API.")

        # 2. Live Tennis API (без коэффициентов)
        events, error2 = get_tennis_events_legacy()
        if events:
            return events, f"Источник: Live Tennis API (без коэф.). Найдено: {len(events)}."

        # 3. ESPN (совсем резерв)
        st.warning(f"Live Tennis API недоступен: {error2}. Пробую ESPN.")
        return get_espn_events("tennis")

    if sport == "football":
        return get_espn_events("football")

    if sport == "dota2":
        try:
            r = requests.get("https://api.opendota.com/api/status", timeout=TIMEOUT)
            r.raise_for_status()
            return [], "OpenDota доступен, но не даёт расписания."
        except Exception as e:
            return [], f"OpenDota недоступен: {type(e).__name__}"
    if sport == "cs2":
        return [], "Источник CS2 не подключён."

    return [], "Нет доступных матчей."

def source_status():
    out = {}
    try:
        api_key = st.secrets.get("PINNWIRE_API_KEY", "")
        out["PinnWire"] = "ключ есть" if api_key else "ключ не настроен"
    except Exception:
        out["PinnWire"] = "ошибка"
    try:
        api_key = st.secrets.get("LIVETENNIS_API_KEY", "")
        out["Live Tennis API"] = "ключ есть" if api_key else "ключ не настроен"
    except Exception:
        out["Live Tennis API"] = "ошибка"
    out["ESPN"] = "резервный источник"
    out["BetBoom"] = "не подключён"
    return out
