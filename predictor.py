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

def adjust_with_stats(prob_home, stats, tour="atp"):
    if not stats:
        return prob_home, 0.0

    home = stats.get("home", {})
    away = stats.get("away", {})

    # 1. Форма (макс разница 0.3)
    fh = (home.get("form") or {}).get("win_rate", 0.5)
    fa = (away.get("form") or {}).get("win_rate", 0.5)
    form_diff = max(-0.3, min(0.3, fh - fa))

    # 2. H2H (макс разница 1.0)
    h2h = home.get("h2h") or {}
    h2h_diff = 0.0
    if h2h.get("total", 0) >= 3:
        h2h_diff = max(-1.0, min(1.0, (h2h["a_wins"] - h2h["b_wins"]) / h2h["total"]))

    # 3. Отдых (макс разница 7 дней)
    rh, ra = home.get("rest"), away.get("rest")
    rest_diff = 0.0
    if rh is not None and ra is not None and rh < 30 and ra < 30:
        rest_diff = max(-7, min(7, rh - ra)) / 7.0

    # 4. Покрытие (макс разница 0.4)
    sh = (home.get("surface") or {}).get("win_rate")
    sa = (away.get("surface") or {}).get("win_rate")
    surface_diff = max(-0.4, min(0.4, sh - sa)) if (sh is not None and sa is not None) else 0.0
        
    # 5. Подача, Прием, Усталость (жестко ограничиваем)
    adv_h, adv_a = home.get("advanced") or {}, away.get("advanced") or {}
    
    serve_h, serve_a = adv_h.get("serve_rating"), adv_a.get("serve_rating")
    ret_h, ret_a = adv_h.get("return_rating"), adv_a.get("return_rating")
    min_h, min_a = adv_h.get("fatigue_minutes"), adv_a.get("fatigue_minutes")
    
    # Подача: разница не больше 10%
    serve_diff = max(-0.1, min(0.1, serve_h - serve_a)) if (serve_h and serve_a) else 0.0
    
    # Прием: разница не больше 10%
    ret_diff = max(-0.1, min(0.1, ret_h - ret_a)) if (ret_h and ret_a) else 0.0
    
    # Усталость: делим на 120, но ОГРАНИЧИВАЕМ до +/- 3 (чтобы не было выбросов)
    fatigue_diff = 0.0
    if min_h is not None and min_a is not None:
        raw_diff = (min_a - min_h) / 120.0
        fatigue_diff = max(-3.0, min(3.0, raw_diff))

    # Веса из оптимизатора (Прием сделали положительным вручную, так как ML ошибся)
    if tour == "wta":
        w_elo, w_form, w_h2h, w_rest, w_surf, w_serve, w_ret, w_fatigue = (
            1.3845, -0.0736, -0.0054, -1.7219, 0.5488, 0.2576, 0.2000, -0.1899
        )
    else: # atp
        w_elo, w_form, w_h2h, w_rest, w_surf, w_serve, w_ret, w_fatigue = (
            1.0768, -0.0282, -0.0181, -1.8373, 0.8412, 0.5935, 0.3000, -0.3319
        )

    prob_home_safe = max(0.01, min(0.99, prob_home))
    elo_log_odds = np.log(prob_home_safe / (1 - prob_home_safe))

    new_log_odds = (
        (w_elo * elo_log_odds) + (w_form * form_diff) + (w_h2h * h2h_diff) + 
        (w_rest * rest_diff) + (w_surf * surface_diff) + (w_serve * serve_diff) + 
        (w_ret * ret_diff) + (w_fatigue * fatigue_diff)
    )

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
