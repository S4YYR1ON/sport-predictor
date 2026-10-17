import pandas as pd
import re
import numpy as np 


def find_elo_player(elo_dict, player_name):
    if not player_name or not elo_dict:
        return None
    
    # 1. Прямое совпадение (идеально)
    if player_name in elo_dict:
        return elo_dict[player_name]
    
    parts = player_name.strip().split()
    if not parts:
        return None
    
    last_name = parts[-1].lower()
    # 2. Ищем по фамилии с проверкой границ слов (чтобы "Li" не находил "Cilic")
    pattern = re.compile(r'\b' + re.escape(last_name) + r'\b', re.IGNORECASE)
    
    best_match = None
    for key, val in elo_dict.items():
        if pattern.search(key):
            # Если нашли несколько, берем того, чье имя длиннее (наиболее точное совпадение)
            if best_match is None or len(key) < len(best_match[0]):
                best_match = (key, val)
                
    if best_match:
        return best_match[1]
        
    return None


def calibrate(p):
    if p > 0.5:
        return p - 0.05 * (p - 0.5)
    return p + 0.05 * (0.5 - p)


def adjust_with_stats(prob_home, stats, tour="atp"):
    """
    Корректирует вероятность с учётом ML-весов (Log-Odds).
    """
    if not stats:
        return prob_home, 0.0

    home = stats.get("home", {})
    away = stats.get("away", {})

    # 1. Считаем deltas (разницы), как в оптимизаторе
    # Форма
    fh = (home.get("form") or {}).get("win_rate", 0.5)
    fa = (away.get("form") or {}).get("win_rate", 0.5)
    form_diff = fh - fa

    # H2H
    h2h = home.get("h2h") or {}
    h2h_diff = 0.0
    if h2h.get("total", 0) >= 3:
        h2h_diff = (h2h["a_wins"] - h2h["b_wins"]) / h2h["total"]

    # Отдых
    rh = home.get("rest")
    ra = away.get("rest")
    rest_diff = 0.0
    if rh is not None and ra is not None and rh < 30 and ra < 30:
        rest_diff = max(-7, min(7, rh - ra)) / 7.0

    # Покрытие
    sh = (home.get("surface") or {}).get("win_rate")
    sa = (away.get("surface") or {}).get("win_rate")
    surface_diff = 0.0
    if sh is not None and sa is not None:
        surface_diff = sh - sa

    # 2. Веса из оптимизатора (используем ATP по умолчанию, они близки)
    # Если хочешь идеал, передавай tour в функцию и делай if tour == "wta": ...
    if tour == "wta":
        w_elo, w_form, w_h2h, w_rest, w_surf = 1.0375, -0.2884, 0.0396, -1.8298, 0.4227
    else:
        w_elo, w_form, w_h2h, w_rest, w_surf = 1.0725, -0.3906, 0.1796, -1.7684, 0.0594

    # 3. Переводим вероятность Elo в Log-Odds
    prob_home_safe = max(0.01, min(0.99, prob_home))
    elo_log_odds = np.log(prob_home_safe / (1 - prob_home_safe))

    # 4. Считаем новый Log-Odds
    new_log_odds = (
        (w_elo * elo_log_odds) + 
        (w_form * form_diff) + 
        (w_h2h * h2h_diff) + 
        (w_rest * rest_diff) + 
        (w_surf * surface_diff)
    )

    # 5. Переводим обратно в вероятность
    new_prob = 1 / (1 + np.exp(-new_log_odds))
    
    # Ограничиваем, чтобы не было 0% или 100%
    new_prob = max(0.05, min(0.95, new_prob))
    
    # Вычисляем чистую разницу (для вывода в UI)
    adj = new_prob - prob_home

    return new_prob, adj


def predict(sport, event, elo_dict=None, surface="hard", stats=None):
    a = event.get("home", "Участник A")
    b = event.get("away", "Участник B")

    # ===== Elo + калибровка + корректировка =====
    if elo_dict:
        elo_a = find_elo_player(elo_dict, a)
        elo_b = find_elo_player(elo_dict, b)
        if elo_a and elo_b:
            surface_key = {"hard": "hElo", "clay": "cElo", "grass": "gElo"}.get(
                surface, "elo"
            )
            elo_a_val = elo_a.get(surface_key) if isinstance(elo_a, dict) else elo_a
            elo_b_val = elo_b.get(surface_key) if isinstance(elo_b, dict) else elo_b
            if not elo_a_val or not elo_b_val or pd.isna(elo_a_val) or pd.isna(elo_b_val):
                elo_a_val = elo_a.get("elo") if isinstance(elo_a, dict) else elo_a
                elo_b_val = elo_b.get("elo") if isinstance(elo_b, dict) else elo_b

            if elo_a_val and elo_b_val:
                prob_a = 1 / (1 + 10 ** ((elo_b_val - elo_a_val) / 400))
                prob_a = calibrate(prob_a)
                prob_a, adj = adjust_with_stats(prob_a, stats)
                prob_b = 1 - prob_a

                if prob_a >= prob_b:
                    selection = f"Победа {a}"
                    probability = prob_a
                    fav, dog = a, b
                else:
                    selection = f"Победа {b}"
                    probability = prob_b
                    fav, dog = b, a

                surface_ru = {"hard": "хард", "clay": "грунт", "grass": "трава"}.get(
                    surface, "хард"
                )
                explanation = (
                    f"Прогноз на основе Elo-рейтингов Tennis Abstract ({surface_ru}) "
                    f"с калибровкой и корректировкой по форме/H2H/отдыху/покрытию. "
                    f"{a} ({elo_a_val:.0f}) vs {b} ({elo_b_val:.0f}). "
                    f"Вероятность победы {fav} — {probability:.1%}, "
                    f"{dog} — {1 - probability:.1%}. "
                    f"Корректировка: {adj:+.1%}."
                )
                confidence = f"средняя — Elo + калибровка + все факторы ({surface_ru})"

                return {
                    "selection": selection,
                    "probability": probability,
                    "odds": None,
                    "fair_odds": 1 / probability,
                    "edge": None,
                    "explanation": explanation,
                    "confidence": confidence,
                    "adjustment": adj,
                }

    # ===== Fallback =====
    try:
        oa = float(event.get("odds_home")) if event.get("odds_home") else None
    except (TypeError, ValueError):
        oa = None
    try:
        ob = float(event.get("odds_away")) if event.get("odds_away") else None
    except (TypeError, ValueError):
        ob = None

    if oa and ob and oa > 1 and ob > 1:
        pa, pb = 1 / oa, 1 / ob
        market_a = pa / (pa + pb)
        market_b = 1 - market_a
        if market_a >= market_b:
            selection = f"Победа {a}"
            p = max(0.05, min(0.95, 0.85 * market_a + 0.15 * 0.5))
            odds = oa
            mfav = market_a
        else:
            selection = f"Победа {b}"
            p = max(0.05, min(0.95, 0.85 * market_b + 0.15 * 0.5))
            odds = ob
            mfav = market_b

        explanation = (
            f"Оценка на основе коэффициентов Pinnacle. "
            f"Рыночная вероятность {a} — {market_a:.1%}, {b} — {market_b:.1%}. "
            f"Фаворит: {selection.split('Победа ')[1]} ({mfav:.1%} по рынку)."
        )
        return {
            "selection": selection,
            "probability": p,
            "odds": odds,
            "fair_odds": 1 / p,
            "edge": p * odds - 1,
            "explanation": explanation,
            "confidence": "низкая — нет независимой модели",
            "adjustment": 0.0,
        }

    return {
        "selection": "Недостаточно данных для выбора",
        "probability": 0.5,
        "odds": None,
        "fair_odds": 2.0,
        "edge": None,
        "explanation": "Нет проверенных коэффициентов и статистики.",
        "confidence": "очень низкая",
        "adjustment": 0.0,
    }
