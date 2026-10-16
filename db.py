import streamlit as st
from st_supabase_connection import SupabaseConnection

conn = st.connection("supabase", type=SupabaseConnection)


def init_db():
    """Таблица создана вручную в Supabase."""
    pass


def save_prediction(sport, event, selection, probability, odds, explanation, confidence):
    data = {
        "sport": sport,
        "event": event,
        "selection": selection,
        "probability": probability,
        "odds": odds,
        "explanation": explanation,
        "confidence": confidence,
    }
    result = conn.table("predictions").insert(data).execute()
    return result.data[0]["id"] if result.data else None


def list_predictions(limit=100):
    result = (
        conn.table("predictions")
        .select("*")
        .order("id", desc=True)
        .limit(limit)
        .execute()
    )
    data = result.data
    if isinstance(data, dict):
        return [data]
    if not data:
        return []
    return data


def settle_prediction(pid, result_status):
    pred = (
        conn.table("predictions")
        .select("*")
        .eq("id", pid)
        .eq("status", "open")
        .execute()
    )
    if not pred.data:
        return False
    row = pred.data[0]
    profit = (
        (row["odds"] - 1)
        if result_status == "won" and row["odds"]
        else (-1 if result_status == "lost" else 0)
    )
    conn.table("predictions").update(
        {"status": result_status, "profit": profit}
    ).eq("id", pid).execute()
    return True


def update_closing_odds(pid, closing_odds):
    """Сохраняет closing line Pinnacle и считает CLV."""
    pred = conn.table("predictions").select("*").eq("id", pid).execute()
    if not pred.data:
        return False
    row = pred.data[0]
    bet_odds = row.get("odds")
    clv = None
    if bet_odds and closing_odds and closing_odds > 1:
        clv = (bet_odds / closing_odds) - 1
    conn.table("predictions").update(
        {"closing_odds": closing_odds, "clv": clv}
    ).eq("id", pid).execute()
    return True


def clv_summary():
    """Средний CLV по всем прогнозам."""
    result = (
        conn.table("predictions")
        .select("clv")
        .not_.is_("clv", "null")
        .execute()
    )
    rows = result.data or []
    clvs = [r["clv"] for r in rows if r.get("clv") is not None]
    if not clvs:
        return {"count": 0, "avg_clv": None, "positive": 0}
    return {
        "count": len(clvs),
        "avg_clv": sum(clvs) / len(clvs),
        "positive": sum(1 for c in clvs if c > 0),
    }


def summary():
    result = (
        conn.table("predictions")
        .select("status, profit")
        .neq("status", "open")
        .execute()
    )
    rows = result.data or []
    return {
        "settled": len(rows),
        "won": sum(1 for r in rows if r["status"] == "won"),
        "lost": sum(1 for r in rows if r["status"] == "lost"),
        "profit": sum(r["profit"] or 0 for r in rows),
    }
