import requests
import streamlit as st
import pandas as pd
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

TOURNAMENT_SURFACE = {
    "australian open": "hard", "roland garros": "clay", "french open": "clay",
    "wimbledon": "grass", "us open": "hard", "indian wells": "hard",
    "miami": "hard", "monte carlo": "clay", "madrid": "clay", "rome": "clay",
    "canada": "hard", "cincinnati": "hard", "shanghai": "hard",
    "paris masters": "hard", "vienna": "hard", "basel": "hard",
    "halle": "grass", "queens": "grass", "barcelona": "clay",
    "hamburg": "clay", "tokyo": "hard", "beijing": "hard", "dubai": "hard",
    "acapulco": "hard", "rio": "clay", "doha": "hard", "charleston": "clay",
    "stuttgart": "clay", "eastbourne": "grass", "berlin": "grass",
    "wuhan": "hard", "guadalajara": "hard",
}

def get_surface(league_name):
    if not league_name:
        return "hard"
    name_lower = league_name.lower()
    for keyword, surface in TOURNAMENT_SURFACE.items():
        if keyword in name_lower:
            return surface
    return "hard"

@st.cache_data(ttl=600)
def get_pinnapi_tennis_events():
    try:
        api_key = st.secrets["PINNAPI_API_KEY"]
    except (KeyError, FileNotFoundError):
        return None, "Ключ Pinnapi не настроен."

    # Правильный базовый URL и эндпоинт из документации
    url = "https://pinnapi.com/kit/v1/prematch/fixtures"
    headers = {"x-portal-apikey": api_key}
    # sport_id=2 — это теннис (согласно документации)
    params = {"sport_id": 2} 

    try:
        r = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        
        # В ответе ожидаем список событий (fixtures). 
        # Структура может быть в корне или внутри ключа 'events'/'fixtures'
        events_list = data if isinstance(data, list) else data.get("events", data.get("fixtures", []))
        
        if not events_list:
            return [], "Pinnapi не вернул событий."

        now_utc = datetime.utcnow()
        events = []
        for ev in events_list:
            # Пытаемся достать дату начала (может называться start, starts, start_time)
            start_ts = ev.get("start") or ev.get("starts") or ev.get("start_time") or ""
            
            # Пропускаем прошедшие матчи
            try:
                clean = start_ts.split(".")[0].replace("Z", "")
                dt = datetime.fromisoformat(clean)
                if dt < now_utc:
                    continue
            except Exception:
                pass

            # Имена игроков
            home = ev.get("home")
            away = ev.get("away")
            if not home or not away:
                continue
            
            # Фильтр от парных матчей (там в именах бывает "/")
            if "/" in home or "/" in away:
                continue

            # Ищем коэффициенты Moneyline. 
            # В зависимости от структуры они могут быть в 'periods', 'markets' или сразу в корне.
            odds_home = None
            odds_away = None
            
            # Вариант 1: Коэфы лежат в periods (как в старом коде)
            periods = ev.get("periods") or {}
            main = periods.get("num_0") or {}
            ml = main.get("money_line")
            if isinstance(ml, dict):
                odds_home = ml.get("home")
                odds_away = ml.get("away")
            
            # Вариант 2: Коэфы лежат в markets (более вероятно для kit/v1)
            if not odds_home:
                markets = ev.get("markets") or []
                for m in markets:
                    if m.get("type") == "moneyline" or m.get("name") == "Moneyline":
                        # В некоторых API это список исходов
                        outcomes = m.get("outcomes") or []
                        for o in outcomes:
                            if o.get("type") == "home": odds_home = o.get("price")
                            if o.get("type") == "away": odds_away = o.get("price")
                        # В других — просто поля home/away
                        if not odds_home:
                            odds_home = m.get("home")
                            odds_away = m.get("away")

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

        return events, f"Pinnapi: найдено матчей {len(events)}."
    except Exception as e:
        return None, f"Ошибка Pinnapi: {type(e).__name__} - {e}"

@st.cache_data(ttl=86400)
def get_elo_ratings(tour="atp"):
    # ... код не меняется, он работает ...
    if tour not in ("atp", "wta"):
        return {}, "Тур должен быть 'atp' или 'wta'"

    url = f"https://tennisabstract.com/reports/{tour}_elo_ratings.html"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        from io import StringIO
        tables = pd.read_html(StringIO(response.text))
        if len(tables) < 2:
            return {}, "Не найдена таблица с рейтингами."
        df = tables[1].copy()
        df.columns = [str(c).replace("\xa0", " ").strip() for c in df.columns]
        if "Player" not in df.columns or "Elo" not in df.columns:
            return {}, f"Не найдены колонки Player/Elo."
        df["Elo"] = pd.to_numeric(df["Elo"], errors="coerce")
        df["Player"] = df["Player"].astype(str).str.strip()
        df = df.dropna(subset=["Elo", "Player"])

        elo_dict = {}
        for _, row in df.iterrows():
            elo_dict[row["Player"]] = {
                "elo": row["Elo"],
                "hElo": pd.to_numeric(row.get("hElo"), errors="coerce"),
                "cElo": pd.to_numeric(row.get("cElo"), errors="coerce"),
                "gElo": pd.to_numeric(row.get("gElo"), errors="coerce"),
            }
        return elo_dict, None
    except Exception as e:
        return {}, f"Ошибка Elo: {type(e).__name__} - {e}"

# Заглушка для Bet Better (так как мы не знаем её API)
def get_all_betbetter_picks():
    return [], "Интеграция Bet Better временно отключена (нет публичного API)"

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"
ESPN_PATHS = {
    "football": [
        ("soccer/eng.1", "Английская Премьер-лига"),
        ("soccer/uefa.champions", "Лига чемпионов"),
    ],
}

def get_espn_events(sport):
    events, errors = [], []
    for path, label in ESPN_PATHS.get(sport, []):
        try:
            r = requests.get(
                f"{ESPN_BASE}/{path}/scoreboard",
                timeout=TIMEOUT,
                headers={"User-Agent": "SportPredictorMVP/1.0"},
            )
            r.raise_for_status()
            for ev in r.json().get("events", []):
                comps = ev.get("competitions", [])
                competitors = comps[0].get("competitors", []) if comps else []
                if len(competitors) < 2:
                    continue
                home = next(
                    (x for x in competitors if x.get("homeAway") == "home"),
                    competitors[0],
                )
                away = next(
                    (x for x in competitors if x.get("homeAway") == "away"),
                    competitors[1],
                )
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
    warning = (
        ("Часть источников недоступна: " + "; ".join(errors))
        if errors
        else "Источник: ESPN."
    )
    return events, warning

def get_events(sport, region="all", tour_filter="all"):
    if sport == "tennis":
        # Временно возвращаем заглушку для тенниса, если Pinnapi не работает
        # return [], "Pinnapi временно отключен"
        
        # Раскомментируй это, когда настроишь запросы к Pinnapi
        events, error = get_pinnapi_tennis_events()
        if events:
            if region == "europe":
                events = [e for e in events if is_european_league(e.get("league_name", ""))]
            if tour_filter == "top":
                events = [e for e in events if is_top_tournament(e.get("league_name", ""))]
            return events, f"Источник: Pinnapi (Pinnacle). Найдено матчей: {len(events)}."
        return [], f"Pinnapi недоступен: {error}"

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
        api_key = st.secrets.get("PINNAPI_API_KEY", "")
        out["Pinnapi"] = "ключ есть" if api_key else "ключ не настроен"
    except Exception:
        out["Pinnapi"] = "ошибка"
    out["ESPN"] = "резервный источник"
    out["BetBoom"] = "не подключён"
    return out
