import pandas as pd
import requests
import streamlit as st
from io import StringIO

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
def compute_match_stats(tour, home_name, away_name, surface="hard", match_date=None):
    df = load_matches(tour=tour)
    if df.empty:
        return None
    return {
        "home": {
            "form": get_player_form(df, home_name, n=10),
            "h2h": get_h2h(df, home_name, away_name),
            "rest": get_rest_days(df, home_name, before_date=match_date),
            "surface": get_surface_winrate(df, home_name, surface),
        },
        "away": {
            "form": get_player_form(df, away_name, n=10),
            "h2h": get_h2h(df, away_name, home_name),
            "rest": get_rest_days(df, away_name, before_date=match_date),
            "surface": get_surface_winrate(df, away_name, surface),
        },
    }
