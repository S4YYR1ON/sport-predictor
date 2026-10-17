import pandas as pd
import numpy as np
import requests
from io import StringIO
from collections import defaultdict
from sklearn.linear_model import LogisticRegression

SACKMANN_BASE = "https://raw.githubusercontent.com/Aneeshers/tennis-sackmann-archive/main"

def load_historical(tour="atp", start_year=2015, end_year=2025):
    all_matches = []
    for year in range(start_year, end_year + 1):
        url = f"{SACKMANN_BASE}/{tour}/{tour}_matches_{year}.csv"
        try:
            r = requests.get(url, timeout=25)
            r.raise_for_status()
            df = pd.read_csv(StringIO(r.text), low_memory=False)
            all_matches.append(df)
        except Exception:
            pass
    df = pd.concat(all_matches, ignore_index=True)
    df["tourney_date"] = pd.to_datetime(df["tourney_date"], format="%Y%m%d", errors="coerce")
    return df.sort_values("tourney_date").reset_index(drop=True)

def calibrate(p):
    if p > 0.5:
        return p - 0.05 * (p - 0.5)
    return p + 0.05 * (0.5 - p)

def run_optimization(tour="atp"):
    print(f"Загрузка данных {tour.upper()}...")
    df = load_historical(tour)
    
    elo = defaultdict(lambda: 1500)
    last_match_date = {}
    match_history = defaultdict(list)
    h2h_history = defaultdict(lambda: [0, 0])
    
    # Будем собирать фичи для ML
    X = [] # Признаки
    y = [] # Таргет (1 - победил home, 0 - проиграл)

    for _, row in df.iterrows():
        w = row["winner_name"]
        l = row["loser_name"]
        date = row["tourney_date"]
        surface = row.get("surface", "Hard")
        
        if pd.isna(w) or pd.isna(l) or pd.isna(date):
            continue
            
        ew, el = elo[w], elo[l]
        prob_w_base = 1 / (1 + 10 ** ((el - ew) / 400))
        prob_w_calib = calibrate(prob_w_base)
        
        # Считаем разницу (deltas)
        fw = sum(1 for m in match_history[w][-10:] if m["won"]) / 10.0 if match_history[w] else 0.5
        fl = sum(1 for m in match_history[l][-10:] if m["won"]) / 10.0 if match_history[l] else 0.5
        form_diff = fw - fl
        
        key = tuple(sorted([w, l]))
        hw, hl = h2h_history[key]
        h2h_diff = 0.0
        if hw + hl >= 3:
            w_wins = hw if key[0] == w else hl
            l_wins = hl if key[0] == w else hw
            h2h_diff = (w_wins - l_wins) / (hw + hl)
            
        rest_diff = 0.0
        if w in last_match_date and l in last_match_date:
            rw = (date - last_match_date[w]).days
            rl = (date - last_match_date[l]).days
            if rw < 30 and rl < 30:
                rest_diff = max(-7, min(7, rw - rl)) / 7.0 # Нормализуем от -1 до 1
                
        sw = [m for m in match_history[w] if m["surface"] == surface]
        sl = [m for m in match_history[l] if m["surface"] == surface]
        surface_diff = 0.0
        if sw and sl:
            sw_rate = sum(1 for m in sw if m["won"]) / len(sw)
            sl_rate = sum(1 for m in sl if m["won"]) / len(sl)
            surface_diff = sw_rate - sl_rate

        # Собираем данные только с 2018 года
        if date.year >= 2018:
            # ВАЖНО: Мы подаем в ML не саму вероятность, а логарифм шансов (log-odds) от Elo
            elo_log_odds = np.log(prob_w_calib / (1 - prob_w_calib))
            
            X.append([elo_log_odds, form_diff, h2h_diff, rest_diff, surface_diff])
            y.append(1) # Победитель
            
            # Зеркальный матч (если бы победил l): для баланса данных
            # (В реальном коде можно сделать, но для простоты обучимся только на победителях)

        # Обновляем стейт
        elo[w] = ew + 32 * (1 - prob_w_base)
        elo[l] = el + 32 * (0 - (1 - prob_w_base))
        last_match_date[w] = date
        last_match_date[l] = date
        match_history[w].append({"date": date, "surface": surface, "won": True})
        match_history[l].append({"date": date, "surface": surface, "won": False})
        
        if key[0] == w: h2h_history[key][0] += 1
        else: h2h_history[key][1] += 1

    X = np.array(X)
    y = np.array(y)

    # Обучаем логистическую регрессию
    # C=1.0 - стандартная регуляризация. fit_intercept=False, так как log_odds уже отцентрован.
    clf = LogisticRegression(fit_intercept=False, C=1.0)
    clf.fit(X, y)

    coefs = clf.coef_[0]
    print(f"\n=== ОПТИМАЛЬНЫЕ ВЕСА ДЛЯ {tour.upper()} ===")
    print(f"1. Elo (Log-Odds): {coefs[0]:.4f}  (должен быть около 1.0)")
    print(f"2. Форма:          {coefs[1]:.4f}  (раньше было 0.03)")
    print(f"3. H2H:            {coefs[2]:.4f}  (раньше было 0.02)")
    print(f"4. Отдых:          {coefs[3]:.4f}  (раньше было 0.003)")
    print(f"5. Покрытие:       {coefs[4]:.4f}  (раньше было 0.02)")
    
if __name__ == "__main__":
    run_optimization("atp")
    run_optimization("wta")
