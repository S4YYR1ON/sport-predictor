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

# Заменяем библиотеку pinnapi на прямой запрос requests (если у Pinnapi есть REST API)
@st.cache_data(ttl=600)
def get_pinnapi_tennis_events():
    """
    ВРЕМЕННАЯ ЗАГЛУШКА. 
    Возвращает фейковые матчи, чтобы не ломать приложение, пока мы не узнаем 
    точный URL API для Pinnacle.
    """
    try:
        api_key = st.secrets["PINNAPI_API_KEY"]
        if not api_key:
            return [], "Ключ Pinnapi не настроен."
    except (KeyError, FileNotFoundError):
        return [], "Ключ Pinnapi не настроен в секретах."

    # Генерируем тестовые события, чтобы интерфейс работал
    events = [
        {
            "home": "Novak Djokovic",
            "away": "Carlos Alcaraz",
            "start": "2024-05-20T14:00:00Z",
            "source": "Тестовый источник (Заглушка)",
            "odds_home": 1.85,
            "odds_away": 1.95,
            "match_id": "test1",
            "league_name": "ATP Masters 1000",
        },
        {
            "home": "Aryna Sabalenka",
            "away": "Iga Swiatek",
            "start": "2024-05-21T12:00:00Z",
            "source": "Тестовый источник (Заглушка)",
            "odds_home": 2.10,
            "odds_away": 1.75,
            "match_id": "test2",
            "league_name": "WTA 1000",
        }
    ]
    
    return events, "Внимание: Pinnapi временно работает в режиме заглушки (тестовые матчи)."

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
