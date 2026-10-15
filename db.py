import sqlite3
from pathlib import Path
DB=Path(__file__).with_name("predictions.sqlite3")
def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init_db():
    with connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS predictions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,sport TEXT,event TEXT,selection TEXT,
        probability REAL,odds REAL,explanation TEXT,confidence TEXT,
        status TEXT DEFAULT 'open',profit REAL,created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
def save_prediction(sport,event,selection,probability,odds,explanation,confidence):
    with connect() as c:
        cur=c.execute("INSERT INTO predictions(sport,event,selection,probability,odds,explanation,confidence) VALUES(?,?,?,?,?,?,?)",
        (sport,event,selection,probability,odds,explanation,confidence))
        return cur.lastrowid
def list_predictions(limit=100):
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM predictions ORDER BY id DESC LIMIT ?",(limit,)).fetchall()]
def settle_prediction(pid,result):
    with connect() as c:
        r=c.execute("SELECT * FROM predictions WHERE id=? AND status='open'",(pid,)).fetchone()
        if not r: return False
        profit=(r["odds"]-1) if result=="won" and r["odds"] else (-1 if result=="lost" else 0)
        c.execute("UPDATE predictions SET status=?,profit=? WHERE id=?",(result,profit,pid))
        return True
def summary():
    with connect() as c: rows=c.execute("SELECT status,profit FROM predictions WHERE status!='open'").fetchall()
    return {"settled":len(rows),"won":sum(r["status"]=="won" for r in rows),"lost":sum(r["status"]=="lost" for r in rows),
            "profit":sum(r["profit"] or 0 for r in rows)}
