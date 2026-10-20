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


import numpy as np # Обязательно добавь в самый верх файла predictor.py

import numpy as np

import numpy as np

import numpy as np

import numpy as np

def adjust_with_stats(prob_home, stats, tour="atp"):
    if not stats:
        return prob_home, 0.0

    home = stats.get("home", {})
    away = stats.get("away", {})

    # --- 1. БАЗОВЫЕ 5 ФАКТОРОВ (ML-веса) ---
    fh = (home.get("form") or {}).get("win_rate", 0.5)
    fa = (away.get("form") or {}).get("win_rate", 0.5)
    form_diff = fh - fa

    h2h = home.get("h2h") or {}
    h2h_diff = 0.0
    if h2h.get("total", 0) >= 3:
        h2h_diff = (h2h["a_wins"] - h2h["b_wins"]) / h2h["total"]

    rh, ra = home.get("rest"), away.get("rest")
    rest_diff = 0.0
    if rh is not None and ra is not None and rh < 30 and ra < 30:
        rest_diff = max(-7, min(7, rh - ra)) / 7.0

    sh = (home.get("surface") or {}).get("win_rate")
    sa = (away.get("surface") or {}).get("win_rate")
    surface_diff = 0.0
    if sh is not None and sa is not None:
        surface_diff = sh - sa

    if tour == "wta":
        w_elo, w_form, w_h2h, w_rest, w_surf = 1.0375, -0.2884, 0.0396, -1.8298, 0.4227
    else: # atp
        w_elo, w_form, w_h2h, w_rest, w_surf = 1.0725, -0.3906, 0.1796, -1.7684, 0.0594

    prob_home_safe = max(0.01, min(0.99, prob_home))
    elo_log_odds = np.log(prob_home_safe / (1 - prob_home_safe))

    new_log_odds = (
        (w_elo * elo_log_odds) + 
        (w_form * form_diff) + 
        (w_h2h * h2h_diff) + 
        (w_rest * rest_diff) + 
        (w_surf * surface_diff)
    )

    # --- 2. НОВЫЕ ФАКТОРЫ (с жесткими лимитами) ---
    adv_h, adv_a = home.get("advanced") or {}, away.get("advanced") or {}
    
    # Подача: разница не может дать больше +/- 0.15 к лог-шансам
    serve_h, serve_a = adv_h.get("serve_rating"), adv_a.get("serve_rating")
    if serve_h is not None and serve_a is not None:
        serve_bonus = max(-0.15, min(0.15, (serve_h - serve_a) * 2.0))
        new_log_odds += serve_bonus

    # Прием: разница не может дать больше +/- 0.15 к лог-шансам
    ret_h, ret_a = adv_h.get("return_rating"), adv_a.get("return_rating")
    if ret_h is not None and ret_a is not None:
        ret_bonus = max(-0.15, min(0.15, (ret_h - ret_a) * 2.0))
        new_log_odds += ret_bonus

    # Усталость: разница в 1000 минут дает максимум -0.2 к лог-шансам (вместо -1.5)
    min_h, min_a = adv_h.get("fatigue_minutes"), adv_a.get("fatigue_minutes")
    if min_h is not None and min_a is not None:
        fatigue_penalty = (min_a - min_h) / 1500.0
        # Жесткий лимит: усталость не может отнять больше 20% лог-шансов
        fatigue_penalty = max(-0.2, min(0.2, fatigue_penalty))
        new_log_odds += fatigue_penalty

    # Переводим обратно в вероятность
    new_prob = 1 / (1 + np.exp(-new_log_odds))
    new_prob = max(0.05, min(0.95, new_prob))
    
    adj = new_prob - prob_home
    return new_prob, adj


def predict(sport, event, elo_dict=None, surface="hard", stats=None):
    a = event.get("home", "Участник A")
    b = event.get("away", "Участник B")
    
    tour_key = "wta" if "wta" in (event.get("league_name") or "").lower() else "atp"

    # Безопасно достаем кэфы
    oa = event.get("odds_home")
    ob = event.get("odds_away")
    
    market_a = None
    if oa and ob and float(oa) > 1 and float(ob) > 1:
        pa, pb = 1 / float(oa), 1 / float(ob)
        market_a = pa / (pa + pb)

    # ===== Elo + калибровка + корректировка =====
    if elo_dict:
        elo_a = find_elo_player(elo_dict, a)
        elo_b = find_elo_player(elo_dict, b)
        if elo_a and elo_b:
            surface_key = {"hard": "hElo", "clay": "cElo", "grass": "gElo"}.get(surface, "elo")
            elo_a_val = elo_a.get(surface_key) if isinstance(elo_a, dict) else elo_a
            elo_b_val = elo_b.get(surface_key) if isinstance(elo_b, dict) else elo_b
            
            if not elo_a_val or not elo_b_val or pd.isna(elo_a_val) or pd.isna(elo_b_val):
                elo_a_val = elo_a.get("elo") if isinstance(elo_a, dict) else elo_a
                elo_b_val = elo_b.get("elo") if isinstance(elo_b, dict) else elo_b

            if elo_a_val and elo_b_val:
                prob_a = 1 / (1 + 10 ** ((elo_b_val - elo_a_val) / 400))
                prob_a = calibrate(prob_a)
                prob_a, adj = adjust_with_stats(prob_a, stats, tour=tour_key)
                
                # SANITY CHECK
                is_market_adjusted = False
                
                if market_a is not None:
                    if abs(prob_a - market_a) > 0.25:
                        prob_a = (0.1 * prob_a) + (0.9 * market_a)
                        is_market_adjusted = True

                prob_b = 1 - prob_a

                if prob_a >= prob_b:
                    selection = f"Победа {a}"
                    probability = prob_a
                    odds_val = float(oa) if oa else None
                    fav, dog = a, b
                else:
                    selection = f"Победа {b}"
                    probability = prob_b
                    odds_val = float(ob) if ob else None
                    fav, dog = b, a

                surface_ru = {"hard": "хард", "clay": "грунт", "grass": "трава"}.get(surface, "хард")
                explanation = (
                    f"Прогноз на основе Elo-рейтингов ({surface_ru}) "
                    f"с калибровкой и ML-корректировкой. "
                    f"{a} ({elo_a_val:.0f}) vs {b} ({elo_b_val:.0f}). "
                    f"Вероятность победы {fav} — {probability:.1%}. "
                    f"Корректировка: {adj:+.1%}."
                )
                
                edge = (probability * odds_val - 1) if odds_val else None

                return {
                    "selection": selection,
                    "probability": probability,
                    "odds": odds_val,
                    "fair_odds": 1 / probability,
                    "edge": edge,
                    "explanation": explanation,
                    "confidence": "средняя — Elo + ML-корректировки",
                    "adjustment": adj,
                    "market_adjusted": is_market_adjusted,
                }

    # ===== Fallback =====
    if market_a is not None:
        if market_a >= 0.5:
            selection = f"Победа {a}"
            p = max(0.05, min(0.95, 0.85 * market_a + 0.15 * 0.5))
            odds_val = float(oa)
        else:
            selection = f"Победа {b}"
            p = max(0.05, min(0.95, 0.85 * (1 - market_a) + 0.15 * 0.5))
            odds_val = float(ob)

        explanation = (
            f"Оценка на основе коэффициентов Pinnacle (нет Elo-рейтинга). "
            f"Рыночная вероятность {a} — {market_a:.1%}, {b} — {1-market_a:.1%}. "
        )
        return {
            "selection": selection,
            "probability": p,
            "odds": odds_val,
            "fair_odds": 1 / p,
            "edge": p * odds_val - 1,
            "explanation": explanation,
            "confidence": "средняя — оценка по рынку Pinnacle",
            "adjustment": 0.0,
        }

    return {
        "selection": "Недостаточно данных",
        "probability": 0.5,
        "odds": None,
        "fair_odds": 2.0,
        "edge": None,
        "explanation": "Нет проверенных коэффициентов и статистики.",
        "confidence": "очень низкая",
        "adjustment": 0.0,
    }
