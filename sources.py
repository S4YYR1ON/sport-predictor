import betbetter
import requests
import streamlit as st
from datetime import datetime

TIMEOUT = 10

# ========== PinnWire (теннис + коэффициенты) ==========
PINNWIRE_BASE = "https://pinnwire.com/kit/v1"

@st.cache_data(ttl=600)
def get_pinnwire_tennis_odds():
    """Получает теннисные матчи из PinnWire и обогащает их данными Bet Better."""
    try:
        api_key = st.secrets["PINNWIRE_API_KEY"]
    except (KeyError, FileNotFoundError):
        return None, "Ключ PinnWire не настроен."

    # Загружаем прогнозы Bet Better
    model_data, bb_error = get_betbetter_tennis_picks()

    url = f"{PINNWIRE_BASE}/markets"
    params = {"sport_id": 2, "key": api_key}

    try:
        response = requests.get(url, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()

        matches = data.get("events") or data.get("data") or data.get("markets") or []

        events = []
        for match in matches:
            if not isinstance(match, dict):
                continue

            home = match.get("home") or match.get("home_team") or match.get("player1")
            away = match.get("away") or match.get("away_team") or match.get("player2")

            if not home or not away:
                continue

            def clean_name(n):
                return str(n).replace("(Games)", "").replace("(games)", "").strip()

            home_clean = clean_name(home)
            away_clean = clean_name(away)

            # Коэффициенты из PinnWire
            odds_home = None
            odds_away = None
            periods = match.get("periods") or {}
            main_period = periods.get("num_0") or {}
            money_line = main_period.get("money_line")
            if isinstance(money_line, dict):
                odds_home = money_line.get("home")
                odds_away = money_line.get("away")
            else:
                # Если money_line нет — берём спред -1.5 как приближение
                spreads = main_period.get("spreads") or {}
                spread = spreads.get("-1.5") or {}
                if spread:
                    odds_home = spread.get("home")
                    odds_away = spread.get("away")

            # Данные модели Bet Better
            bb_home = model_data.get(home_clean.lower())
            bb_away = model_data.get(away_clean.lower())

            events.append({
                "home": home_clean,
                "away": away_clean,
                "start": match.get("start_ts") or match.get("starts") or "",
                "source": "PinnWire · Pinnacle" + (" · коэф. есть" if odds_home else " · коэф. нет"),
                "odds_home": odds_home,
                "odds_away": odds_away,
                "match_id": match.get("event_id"),
                # Данные модели Bet Better
                "bb_home_prob": bb_home["probability"] if bb_home else None,
                "bb_home_fair": bb_home["fair_odds"] if bb_home else None,
                "bb_home_conf": bb_home["confidence"] if bb_home else None,
                "bb_away_prob": bb_away["probability"] if bb_away else None,
                "bb_away_fair": bb_away["fair_odds"] if bb_away else None,
                "bb_away_conf": bb_away["confidence"] if bb_away else None,
            })

        return events, None
    except Exception as e:
        return None, f"Ошибка PinnWire: {type(e).__name__} - {e}"
    
# ===================
@st.cache_data(ttl=600)
def get_betbetter_tennis_picks():
    """Получает вероятности и fair odds от модели Bet Better для тенниса."""
    try:
        feed = betbetter.get_picks("tennis/atp")
        picks = feed.get("picks", [])
        st.write("**🔍 Отладка Bet Better — первые 3 прогноза:**")
        st.json(picks[:3] if picks else "Пусто")
        # Строим словарь: ключ — имя игрока, значение — данные модели
        model_data = {}
        for p in picks:
            game = p.get("game", "")
            selection = p.get("selection", "")
            prob = p.get("modelProbabilityPct")
            fair_odds = p.get("fairOdds")
            confidence = p.get("confidence", "")
            if selection:
                model_data[selection.lower()] = {
                    "probability": prob,
                    "fair_odds": fair_odds,
                    "confidence": confidence,
                    "game": game
                }
        return model_data, None
    except Exception as e:
        return {}, f"Ошибка Bet Better: {type(e).__name__} - {e}"
        
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
