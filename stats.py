import pandas as pd
import requests
import streamlit as st
from io import StringIO
import datetime
from livetennisapi import LiveTennisAPI

SACKMANN_BASE = "https://raw.githubusercontent.com/Aneeshers/tennis-sackmann-archive/main"


@st.cache_data(ttl=86400, show_spinner=False)
def load_matches(tour="atp", years=(2021, 2022, 2023, 2024, 2025, 2026)):
    """Загружает матчи ATP/WTA из архива Sackmann."""
    all_matches = []
    base = f"{SACKMANN_BASE}/{tour}"
    for year in years:
        url = f"{base}/{tour}_matches_{year}.csv"
        try:
            r = requests.get(url, timeout=25)
            r.raise_for_status()
            df = pd.read_csv(StringIO(r.text), low_memory=False)
            all_matches.append(df)
        except Exception:
            continue
    if not all_matches:
        return pd.DataFrame()
    df = pd.concat(all_matches, ignore_index=True)
    df["tourney_date"] = pd.to_datetime(
        df["tourney_date"], format="%Y%m%d", errors="coerce"
    )
    df = df.sort_values("tourney_date").reset_index(drop=True)
    return df


def _last_name(name):
    if not name:
        return ""
    parts = str(name).strip().split()
    return parts[-1].lower() if parts else ""


def _find_player_matches(df, player_name):
    last = _last_name(player_name)
    if not last or df.empty:
        return df.iloc[0:0]
    
    # Используем регулярное выражение с \b для точного поиска фамилии
    pattern = r'\b' + last + r'\b'
    mask = (
        df["winner_name"].fillna("").str.contains(pattern, regex=True, case=False)
        | df["loser_name"].fillna("").str.contains(pattern, regex=True, case=False)
    )
    return df[mask]


def get_player_form(df, player_name, n=10):
    player_matches = _find_player_matches(df, player_name)
    if player_matches.empty:
        return None
    
    # Если матчей в архиве основного тура меньше 5 — данных слишком мало для честного винрейта
    if len(player_matches) < 5:
        return {
            "matches": len(player_matches),
            "wins": 0, # Значения не важны, если ниже добавим проверку
            "losses": 0,
            "win_rate": None, # None означает "нет данных"
            "insufficient_data": True
        }

    last_n = player_matches.tail(n)
    last = _last_name(player_name)
    wins = int(
        last_n["winner_name"]
        .fillna("")
        .str.lower()
        .str.contains(last, regex=False)
        .sum()
    )
    return {
        "matches": len(last_n),
        "wins": wins,
        "losses": len(last_n) - wins,
        "win_rate": wins / len(last_n) if len(last_n) > 0 else 0,
        "insufficient_data": False
    }


def get_h2h(df, player_a, player_b):
    last_a = _last_name(player_a)
    last_b = _last_name(player_b)
    if not last_a or not last_b or df.empty:
        return {"a_wins": 0, "b_wins": 0, "total": 0}
    w = df["winner_name"].fillna("").str.lower()
    l = df["loser_name"].fillna("").str.lower()
    mask = (
        (w.str.contains(last_a, regex=False) & l.str.contains(last_b, regex=False))
        | (w.str.contains(last_b, regex=False) & l.str.contains(last_a, regex=False))
    )
    h2h = df[mask]
    if h2h.empty:
        return {"a_wins": 0, "b_wins": 0, "total": 0}
    a_wins = int(
        h2h["winner_name"]
        .fillna("")
        .str.lower()
        .str.contains(last_a, regex=False)
        .sum()
    )
    return {"a_wins": a_wins, "b_wins": len(h2h) - a_wins, "total": len(h2h)}


def get_rest_days(df, player_name, before_date=None):
    player_matches = _find_player_matches(df, player_name)
    if player_matches.empty:
        return None
        
    if before_date:
        try:
            # Правильная обработка таймзон
            before = pd.Timestamp(before_date)
            if before.tz is not None:
                before = before.tz_convert('UTC').tz_localize(None)
        except Exception:
            return None  # Если дата битая, возвращаем None (а не текущее время)
    else:
        return None  # Для прогноза дата матча обязательна
        
    past = player_matches[player_matches["tourney_date"] < before]
    if past.empty:
        return None
        
    # ВАЖНО: tourney_date - это дата начала турнира, погрешность до 14 дней
    return (before - past["tourney_date"].max()).days
@st.cache_data(ttl=3600, show_spinner=False)

@st.cache_data(ttl=3600, show_spinner=False)
def get_live_rest_days(player_name, match_date, tour="atp"):
    """
    Ищет реальные дни отдыха через ESPN.
    Возвращает int (дни) или None (если данных нет).
    """
    if not player_name or not match_date:
        return None

    try:
        # Парсим дату матча (убираем таймзону)
        md = pd.Timestamp(match_date)
        if md.tz is not None:
            md = md.tz_convert('UTC').tz_localize(None)
        md_date = md.date()
    except Exception:
        return None

    # Берем фамилию игрока для поиска (в нижнем регистре)
    last_name = _last_name(player_name)
    if not last_name:
        return None

    # Проверяем последние 14 дней ДО даты матча
    for i in range(1, 15):
        # 1. Сначала считаем дату и делаем запрос
        check_date = md_date - datetime.timedelta(days=i)
        date_str = check_date.strftime("%Y%m%d")
        
        url = f"https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/scoreboard?dates={date_str}"
        
        try:
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                continue
            
            data = r.json()
            events = data.get("events", [])
            
            # 2. Проваливаемся в структуру JSON
            for ev in events:
                groupings = ev.get("groupings", [])
                for group in groupings:
                    competitions = group.get("competitions", [])
                    
                    for comp in competitions:
                        # 3. ТУТ ФИЛЬТР ПАРНЫХ МАТЧЕЙ
                        comp_type = comp.get("type", {}).get("text", "").lower()
                        if "doubles" in comp_type:
                            continue
                            
                        # 4. Ищем игрока
                        for competitor in comp.get("competitors", []):
                            athlete = competitor.get("athlete", {})
                            
                            espn_last_name = str(athlete.get("lastName", "")).lower()
                            espn_display_name = str(athlete.get("displayName", "")).lower()
                            
                            if last_name == espn_last_name or last_name in espn_display_name:
                                return i # Нашли матч в одиночке, возвращаем дни
        except Exception:
            continue

    # Если за 14 дней ничего не нашли
    return None

def get_surface_winrate(df, player_name, surface):
    player_matches = _find_player_matches(df, player_name)
    if player_matches.empty:
        return None
    surface_matches = player_matches[player_matches["surface"] == surface]
    if surface_matches.empty:
        return None
    last = _last_name(player_name)
    wins = int(
        surface_matches["winner_name"]
        .fillna("")
        .str.lower()
        .str.contains(last, regex=False)
        .sum()
    )
    return {
        "matches": len(surface_matches),
        "wins": wins,
        "win_rate": wins / len(surface_matches),
    }


@st.cache_data(ttl=86400, show_spinner=False)
def get_livetennis_form(player_name, tour="atp"):
    """
    Идет в LiveTennis API, если в Sackmann нет данных по игроку.
    Возвращает словарь в том же формате, что и get_player_form.
    """
    try:
        # ВАЖНО: Проверь в документации LiveTennis, какие туры они поддерживают 
        # ('atp', 'wta', 'challenger', 'itf'). 
        # Если 'atp', то для Челленджеров нужно передавать 'challenger'.
        api_tour = "challenger" if tour == "atp" else "itf" 
        
        with LiveTennisAPI(
            api_key=st.secrets["LIVETENNIS_API_KEY"],
            auth_header="bearer"  # <-- явно указываем заголовок
        ) as client:
            # Ищем последние 10 матчей
            matches = client.list_completed_matches(
                tour=api_tour,
                draw="singles",
                player=player_name,
                limit=10
            )
            
            if not matches:
                return None
                
            # Считаем победы
            # Внимание: проверь в документации, как называется поле победителя (winner)
            # Возможно, там нужно сравнивать ID игрока, а не имя.
            wins = sum(1 for m in matches if player_name.lower() in str(m.winner).lower())
            total = len(matches)
            
            return {
                "matches": total,
                "wins": wins,
                "losses": total - wins,
                "win_rate": wins / total if total > 0 else 0,
                "insufficient_data": False
            }
    except Exception as e:
        # ВРЕМЕННО ВЫВОДИМ ОШИБКУ В ИНТЕРФЕЙС
        st.error(f"Ошибка LiveTennis: {type(e).__name__} - {e}")
        return None


@st.cache_data(ttl=86400, show_spinner=False)
def compute_match_stats(tour, home_name, away_name, surface="hard", match_date=None):
    df = load_matches(tour=tour)
    
    # 1. Отдых (ESPN + Sackmann)
    live_rest_home = get_live_rest_days(home_name, match_date, tour)
    live_rest_away = get_live_rest_days(away_name, match_date, tour)
    
    rest_home = live_rest_home if live_rest_home is not None else get_rest_days(df, home_name, before_date=match_date)
    rest_away = live_rest_away if live_rest_away is not None else get_rest_days(df, away_name, before_date=match_date)

    # 2. Форма (Sackmann + LiveTennis)
    form_home = get_player_form(df, home_name, n=10)
    form_away = get_player_form(df, away_name, n=10)
    
    # Если в Sackmann пусто (None) или мало матчей (insufficient_data), идем в LiveTennis
    if not form_home or form_home.get("insufficient_data"):
        live_form_home = get_livetennis_form(home_name, tour)
        if live_form_home:
            form_home = live_form_home
            
    if not form_away or form_away.get("insufficient_data"):
        live_form_away = get_livetennis_form(away_name, tour)
        if live_form_away:
            form_away = live_form_away

    if df.empty and (live_rest_home is None and live_rest_away is None) and not form_home and not form_away:
        return None

    return {
        "home": {
            "form": form_home,
            "h2h": get_h2h(df, home_name, away_name),
            "rest": rest_home,
            "surface": get_surface_winrate(df, home_name, surface),
        },
        "away": {
            "form": form_away,
            "h2h": get_h2h(df, away_name, home_name),
            "rest": rest_away,
            "surface": get_surface_winrate(df, away_name, surface),
        },
    }
