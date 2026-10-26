import requests
import streamlit as st
from datetime import datetime

TIMEOUT = 15

EUROPE_KEYWORDS = [
    "atp", "wta", "challenger", "itf",
    "spain", "france", "italy", "germany", "uk", "england", "sweden",
    "switzerland", "austria", "belgium", "netherlands", "portugal",
    "greece", "turkey", "russia", "poland", "czech", "romania",
    "hungary", "croatia", "serbia", "bulgaria", "denmark", "norway",
    "finland", "ireland", "scotland", "wales", "monaco",
    "mallorca", "paris", "london", "rome", "madrid", "barcelona",
    "berlin", "hamburg", "munich", "vienna", "geneva", "zurich",
    "basel", "stockholm", "copenhagen", "oslo", "helsinki",
    "prague", "warsaw", "budapest", "bucharest", "sofia",
    "zagreb", "belgrade", "istanbul", "athens", "lisbon",
    "amsterdam", "brussels", "dublin", "europe",
]

def is_european_league(league_name):
    if not league_name:
        return False
    name_lower = league_name.lower()
    return any(kw in name_lower for kw in EUROPE_KEYWORDS)

def is_top_tournament(league_name):
    if not league_name:
        return False
    name_lower = league_name.lower()
    exclude = [
        "itf", "challenger", "w15", "w25", "w35", "w50", "w75", "w100",
        "m15", "m25", "wta 125", "atp 125", "125k", "doubles",
    ]
    if any(word in name_lower for word in exclude):
        return False
    return "atp" in name_lower or "wta" in name_lower

@st.cache_data(ttl=300) # Кэш на 5 минут, чтобы кэфы были свежими
def get_pinnapi_tennis_events():
    try:
        api_key = st.secrets["PINNAPI_API_KEY"]
    except (KeyError, FileNotFoundError):
        return None, "Ключ Pinnapi не настроен."

    url = "https://pinnapi.com/kit/v1/prematch/fixtures"
    headers = {"x-portal-apikey": api_key}
    params = {"sport_id": 2} 

    try:
        r = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        if r.status_code == 429:
            return [], "⏳ Pinnapi временно ограничил запросы (слишком много попыток). Подождите 5-10 минут и нажмите кнопку снова."
        r.raise_for_status()
        data = r.json()
        
        events_list = data if isinstance(data, list) else data.get("events", data.get("fixtures", []))
        
        if not events_list:
            return [], "Pinnapi не вернул событий."

        now_utc = datetime.utcnow()
        events = []
        for ev in events_list:
            start_ts = ev.get("start") or ev.get("starts") or ev.get("start_time") or ""
            
            try:
                clean = start_ts.split(".")[0].replace("Z", "")
                dt = datetime.fromisoformat(clean)
                if dt < now_utc:
                    continue
            except Exception:
                pass

            home = ev.get("home")
            away = ev.get("away")
            if not home or not away:
                continue
            
            if "(Games)" in home or "(Games)" in away or "(Sets)" in home or "(Sets)" in away:
                continue
            if "/" in home or "/" in away:
                continue

            odds_home = None
            odds_away = None
            periods = ev.get("periods") or {}
            main = periods.get("num_0") or {}
            ml = main.get("money_line")
            if isinstance(ml, dict):
                odds_home = ml.get("home")
                odds_away = ml.get("away")

            events.append({
                "home": home,
                "away": away,
                "start": start_ts,
                "source": "Pinnapi · Pinnacle (Moneyline)" + (" · коэф. есть" if odds_home else " · коэф. нет"),
                "odds_home": odds_home,
                "odds_away": odds_away,
                "match_id": ev.get("event_id") or ev.get("id"),
                "league_name": ev.get("league_name", ev.get("league", "")),
            })

        return events, f"Источник: Pinnapi (Pinnacle). Найдено матчей: {len(events)}."
    except Exception as e:
        return None, f"Ошибка Pinnapi: {type(e).__name__} - {e}"

def get_events(sport, region="all", tour_filter="all"):
    if sport == "tennis":
        events, error = get_pinnapi_tennis_events()
        if events:
            if region == "europe":
                events = [e for e in events if is_european_league(e.get("league_name", ""))]
            
            if tour_filter == "top":
                events = [e for e in events if is_top_tournament(e.get("league_name", ""))]
            elif tour_filter == "itf":
                events = [e for e in events if not is_top_tournament(e.get("league_name", ""))]
                
            return events, f"Источник: Pinnapi (Pinnacle). Найдено матчей: {len(events)}."
        return [], f"Pinnapi недоступен: {error}"

    return [], "Этот вид спорта отключен в режиме Line Shopping."

def source_status():
    out = {}
    try:
        api_key = st.secrets.get("PINNAPI_API_KEY", "")
        out["Pinnapi"] = "ключ есть" if api_key else "ключ не настроен"
    except Exception:
        out["Pinnapi"] = "ошибка"
    return out
