import requests
import streamlit as st
import pandas as pd
from datetime import datetime
from pinnapi import Client as PinnapiClient, SPORTS
import betbetter

TIMEOUT = 15

# ============================================================
# БАЗОВЫЕ НАСТРОЙКИ
# ============================================================

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
    "amsterdam", "brussels", "dublin", "europe"
]


def is_european_league(league_name):
    """Проверяет, относится ли турнир к Европе по названию."""
    if not league_name:
        return False
    name_lower = league_name.lower()
    return any(kw in name_lower for kw in EUROPE_KEYWORDS)


def is_top_tournament(league_name):
    """Проверяет, относится ли турнир к ATP/WTA (кроме Challenger/ITF)."""
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
    "australian open": "hard",
    "roland garros": "clay",
    "french open": "clay",
    "wimbledon": "grass",
    "us open": "hard",
    "indian wells": "hard",
    "miami": "hard",
    "monte carlo": "clay",
    "madrid": "clay",
    "rome": "clay",
    "canada": "hard",
    "cincinnati": "hard",
    "shanghai": "hard",
    "paris masters": "hard",
    "vienna": "hard",
    "basel": "hard",
    "halle": "grass",
    "queens": "grass",
    "barcelona": "clay",
    "hamburg": "clay",
    "tokyo": "hard",
    "beijing": "hard",
    "dubai": "hard",
    "acapulco": "hard",
    "rio": "clay",
    "doha": "hard",
    "charleston": "clay",
    "stuttgart": "clay",
    "eastbourne": "grass",
    "berlin": "grass",
    "wuhan": "hard",
    "guadalajara": "hard",
}


def get_surface(league_name):
    """Определяет покрытие по названию турнира."""
    if not league_name:
        return "hard"
    name_lower = league_name.lower()
    for keyword, surface in TOURNAMENT_SURFACE.items():
        if keyword in name_lower:
            return surface
    return "hard"


# ============================================================
# PINNAPI (теннис + Moneyline)
# ============================================================

@st.cache_data(ttl=600)
def get_pinnapi_tennis_events():
    """Получает предматчевые теннисные матчи и коэффициенты Moneyline из Pinnapi."""
    try:
        api_key = st.secrets["PINNAPI_API_KEY"]
    except (KeyError, FileNotFoundError):
        return None, "Ключ Pinnapi не настроен."

    try:
        api = PinnapiClient(api_key)
        response = api.prematch_fixtures(sport_id=SPORTS["tennis"])

        events_list = response.get("events", []) if isinstance(response, dict) else []
        if not events_list:
            return [], "Pinnapi не вернул событий."

        now_utc = datetime.utcnow()
        events = []

        for ev in events_list:
            if not isinstance(ev, dict):
                continue
            if ev.get("event_type") != "prematch":
                continue

            start_ts = ev.get("start_ts") or ev.get("starts") or ""
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

            if "(Games)" in home or "(Games)" in away:
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
                "source": "Pinnapi · Pinnacle (Moneyline)"
                + (" · коэф. есть" if odds_home else " · коэф. нет"),
                "odds_home": odds_home,
                "odds_away": odds_away,
                "match_id": ev.get("event_id"),
                "league_name": ev.get("league_name", ""),
            })

        return events, f"Pinnapi: найдено матчей {len(events)}."
    except Exception as e:
        return None, f"Ошибка Pinnapi: {type(e).__name__} - {e}"


# ============================================================
# ELO (Tennis Abstract)
# ============================================================

@st.cache_data(ttl=86400)
def get_elo_ratings(tour="atp"):
    """Скачивает Elo-рейтинги с Tennis Abstract."""
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
            return {}, f"Не найдены колонки Player/Elo. Есть: {list(df.columns)}"

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


# ============================================================
# BET BETTER
# ============================================================

def get_all_betbetter_picks():
    """Получает прогнозы Bet Better для тенниса (ATP + WTA)."""
    all_picks = []
    errors = []
    for tour, label in [("tennis/atp", "ATP"), ("tennis/wta", "WTA")]:
        try:
            feed = betbetter.get_picks(tour)
            picks = feed.get("picks", [])
            for p in picks:
                game = p.get("game", "")
                market = p.get("market", "")
                locked = p.get("locked", False)

                if locked:
                    if market == "Moneyline" and " @ " in game:
                        home, away = game.split(" @ ", 1)
                        all_picks.append({
                            "tour": label,
                            "home": home.strip(),
                            "away": away.strip(),
                            "game_time": p.get("gameTimeUtc", ""),
                            "market": "Moneyline (заблокировано)",
                            "selection": "Откроется в момент начала матча",
                            "probability": None,
                            "fair_odds": None,
                            "confidence": "LOCKED",
                            "verdict": "",
                            "locked": True,
                        })
                    continue

                selection = (p.get("selection") or "").strip()
                if not game or not selection or " @ " not in game:
                    continue

                home, away = game.split(" @ ", 1)
                all_picks.append({
                    "tour": label,
                    "home": home.strip(),
                    "away": away.strip(),
                    "game_time": p.get("gameTimeUtc", ""),
                    "market": market,
                    "selection": selection,
                    "probability": p.get("modelProbabilityPct"),
                    "fair_odds": p.get("fairOdds"),
                    "confidence": p.get("confidence", ""),
                    "verdict": p.get("verdict", ""),
                    "locked": False,
                })
        except Exception as e:
            errors.append(f"{label}: {type(e).__name__}")
    return all_picks, ("Ошибки: " + "; ".join(errors)) if errors else None


# ============================================================
# ESPN (футбол, резерв)
# ============================================================

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


# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================

def get_events(sport, region="all", tour_filter="all"):
    if sport == "tennis":
        events, error = get_pinnapi_tennis_events()
        if events:
            if region == "europe":
                events = [
                    e for e in events if is_european_league(e.get("league_name", ""))
                ]
            if tour_filter == "top":
                events = [
                    e for e in events if is_top_tournament(e.get("league_name", ""))
                ]
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
    try:
        api_key = st.secrets.get("PINNWIRE_API_KEY", "")
        out["PinnWire"] = "ключ есть" if api_key else "не используется"
    except Exception:
        out["PinnWire"] = "ошибка"
    out["ESPN"] = "резервный источник"
    out["BetBoom"] = "не подключён"
    return out
