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
            bb_home = find_bb_data(model_data, home_clean)
            bb_away = find_bb_data(model_data, away_clean)

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
    """Получает вероятности и fair odds от модели Bet Better для тенниса (ATP + WTA)."""
    model_data = {}
    try:
        for tour in ["tennis/atp", "tennis/wta"]:
            try:
                feed = betbetter.get_picks(tour)
            except Exception:
                continue
            picks = feed.get("picks", [])
            for p in picks:
                if p.get("locked"):
                    continue
                game = p.get("game", "")
                selection = (p.get("selection") or "").strip()
                if not game or not selection or " @ " not in game:
                    continue

                home, away = game.split(" @ ", 1)
                home = home.strip()
                away = away.strip()

                prob = p.get("modelProbabilityPct")
                fair_odds = p.get("fairOdds")
                confidence = p.get("confidence", "")
                market = p.get("market", "")

                sel_lower = selection.lower()
                player_key = None
                if sel_lower.startswith(home.lower()):
                    player_key = home.lower()
                elif sel_lower.startswith(away.lower()):
                    player_key = away.lower()

                if player_key:
                    existing = model_data.get(player_key)
                    # Moneyline приоритетнее, чем Handicap
                    if not existing or market == "Moneyline":
                        model_data[player_key] = {
                            "probability": prob,
                            "fair_odds": fair_odds,
                            "confidence": confidence,
                            "market": market,
                        }
        return model_data, None
    except Exception as e:
        return {}, f"Ошибка Bet Better: {type(e).__name__} - {e}"

# ====================
def find_bb_data(model_data, player_name):
    """Ищет данные Bet Better по имени игрока (нечёткое совпадение по фамилии)."""
    if not player_name or not model_data:
        return None
    name_lower = player_name.strip().lower()
    if name_lower in model_data:
        return model_data[name_lower]
    # Поиск по фамилии (последнее слово)
    parts = name_lower.split()
    if parts:
        last_name = parts[-1]
        for key, val in model_data.items():
            if last_name in key:
                return val
    return None
    
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
                
                # Для заблокированных Moneyline — сохраняем как отдельную запись
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
    
def find_pinnwire_match(bb_home, bb_away, pinnwire_events):
    """Ищет матч PinnWire по именам игроков из Bet Better (по фамилии)."""
    def last_name(name):
        clean = str(name).replace("(Games)", "").replace("(games)", "").strip().lower()
        parts = clean.split()
        return parts[-1] if parts else ""

    bb_h = last_name(bb_home)
    bb_a = last_name(bb_away)
    if not bb_h or not bb_a:
        return None

    for ev in pinnwire_events:
        pw_h = last_name(ev.get("home", ""))
        pw_a = last_name(ev.get("away", ""))
        if (bb_h == pw_h and bb_a == pw_a) or (bb_h == pw_a and bb_a == pw_h):
            return ev
    return None


@st.cache_data(ttl=600)
def get_betbetter_with_value():
    """Возвращает прогнозы Bet Better, обогащённые коэффициентами PinnWire и value-расчётом."""
    # Загружаем Bet Better
    all_picks, error = get_all_betbetter_picks()
    if error:
        return [], error

    # Загружаем PinnWire для сопоставления
    pinnwire_events = []
    try:
        api_key = st.secrets["PINNWIRE_API_KEY"]
        url = f"{PINNWIRE_BASE}/markets"
        params = {"sport_id": 2, "key": api_key}
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        if resp.ok:
            data = resp.json()
            pinnwire_events = data.get("events") or data.get("data") or data.get("markets") or []
    except Exception:
        pass  # PinnWire может быть недоступен — работаем без него

    # Обогащаем каждую ставку
    for pick in all_picks:
        market_odd = None
        value = None
        match_found = None

        # Ищем матч в PinnWire
        match = find_pinnwire_match(pick["home"], pick["away"], pinnwire_events)

        if match:
            match_found = match
            periods = match.get("periods") or {}
            main = periods.get("num_0") or {}

            # Определяем, на какую сторону ставим: сравниваем фамилию из selection с home/away
            sel_lower = pick["selection"].lower()
            home_last = str(pick["home"]).split()[-1].lower()
            away_last = str(pick["away"]).split()[-1].lower()

            # Пытаемся найти линию гандикапа в selection (например, "-3.5")
            line = None
            for token in pick["selection"].split():
                try:
                    line = float(token)
                    break
                except ValueError:
                    continue

            # Ищем спред с этой линией
            if line is not None:
                spreads = main.get("spreads") or {}
                spread_key = str(line)
                spread = spreads.get(spread_key) or {}
                if spread:
                    if home_last in sel_lower:
                        market_odd = spread.get("home")
                    elif away_last in sel_lower:
                        market_odd = spread.get("away")

            # Если спред не нашли — пробуем money_line (если он есть)
            if market_odd is None:
                ml = main.get("money_line")
                if isinstance(ml, dict):
                    if home_last in sel_lower:
                        market_odd = ml.get("home")
                    elif away_last in sel_lower:
                        market_odd = ml.get("away")

        # Расчёт value: prob × odd - 1
        prob = pick.get("probability")
        if prob is not None and market_odd:
            value = (prob / 100.0) * market_odd - 1

        pick["market_odd"] = market_odd
        pick["value"] = value
        pick["match_found"] = match_found is not None

    return all_picks, None
from pinnapi import Client as PinnapiClient, SPORTS

@st.cache_data(ttl=600)
def get_pinnapi_tennis_events():
    """Получает предматчевые теннисные матчи и коэффициенты Moneyline из Pinnapi."""
    try:
        api_key = st.secrets["PINNAPI_API_KEY"]
    except (KeyError, FileNotFoundError):
        return None, "Ключ Pinnapi не настроен."

    try:
        api = PinnapiClient(api_key)
        # sport_id=2 — теннис
        fixtures = api.prematch_fixtures(sport_id=SPORTS["tennis"])
        
        events = []
        for fixture in fixtures:
            home = fixture.get("home")
            away = fixture.get("away")
            if not home or not away:
                continue

            odds_home = None
            odds_away = None
            
            # Ищем рынок Moneyline в списке markets
            markets = fixture.get("markets", [])
            for market in markets:
                if market.get("type") == "moneyline":
                    for price in market.get("prices", []):
                        if price.get("designation") == "home":
                            odds_home = price.get("price")
                        elif price.get("designation") == "away":
                            odds_away = price.get("price")
                    break

            events.append({
                "home": home,
                "away": away,
                "start": fixture.get("startTime", ""),
                "source": "Pinnapi · Pinnacle (Moneyline)",
                "odds_home": odds_home,
                "odds_away": odds_away,
                "match_id": fixture.get("id"),
            })
        return events, None
    except Exception as e:
        return None, f"Ошибка Pinnapi: {type(e).__name__} - {e}"
        
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
