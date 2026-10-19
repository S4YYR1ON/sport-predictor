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
    
    # Определяем тур для правильных ML-весов
    league_name = (event.get("league_name") or "").lower()
    tour_key = "wta" if "wta" in league_name else "atp"

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
            
            # Если данных по покрытию нет, берем общий Elo
            if not elo_a_val or not elo_b_val or pd.isna(elo_a_val) or pd.isna(elo_b_val):
                elo_a_val = elo_a.get("elo") if isinstance(elo_a, dict) else elo_a
                elo_b_val = elo_b.get("elo") if isinstance(elo_b, dict) else elo_b

            if elo_a_val and elo_b_val:
                prob_a = 1 / (1 + 10 ** ((elo_b_val - elo_a_val) / 400))
                prob_a = calibrate(prob_a)
                
                # Вот здесь мы применяем ML-веса
                prob_a, adj = adjust_with_stats(prob_a, stats, tour=tour_key)
                
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
                    f"с калибровкой и корректировкой по ML-весам. "
                    f"{a} ({elo_a_val:.0f}) vs {b} ({elo_b_val:.0f}). "
                    f"Вероятность победы {fav} — {probability:.1%}, "
                    f"{dog} — {1 - probability:.1%}. "
                    f"Корректировка: {adj:+.1%}."
                )
                confidence = f"средняя — Elo + ML-корректировки ({surface_ru})"

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

    # ===== Fallback (если нет Elo) =====
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

        # ОБНОВЛЕННЫЙ ТЕКСТ ЗДЕСЬ
        explanation = (
            f"Оценка на основе коэффициентов Pinnacle (у игроков нет Elo-рейтинга для независимой модели). "
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
            "confidence": "средняя — оценка по рынку Pinnacle (Elo отсутствует)",
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
