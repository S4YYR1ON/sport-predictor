def find_elo_player(elo_dict, player_name):
    """Ищет игрока в словаре Elo по фамилии."""
    if not player_name or not elo_dict:
        return None
    if player_name in elo_dict:
        return elo_dict[player_name]
    parts = player_name.strip().split()
    if not parts:
        return None
    last_name = parts[-1].lower()
    for key, val in elo_dict.items():
        if last_name in key.lower():
            return val
    return None
    
def predict(sport, event, elo_dict=None):
    a = event.get("home", "Участник A")
    b = event.get("away", "Участник B")
    
    # ===== Приоритет 1: Elo-модель =====
    if elo_dict:
        elo_a = find_elo_player(elo_dict, a)
        elo_b = find_elo_player(elo_dict, b)
        if elo_a and elo_b:
            elo_a_val = elo_a.get("elo")
            elo_b_val = elo_b.get("elo")
            prob_a = 1 / (1 + 10 ** ((elo_b_val - elo_a_val) / 400))
            prob_b = 1 - prob_a
            
            if prob_a >= prob_b:
                selection = f"Победа {a}"
                probability = prob_a
                fav = a
                dog = b
            else:
                selection = f"Победа {b}"
                probability = prob_b
                fav = b
                dog = a
            
            fair_odds = 1 / probability
            explanation = (
                f"Прогноз на основе Elo-рейтингов Tennis Abstract: "
                f"{a} ({elo_a:.0f}) vs {b} ({elo_b:.0f}). "
                f"Вероятность победы {fav} — {probability:.1%}, "
                f"{dog} — {1-probability:.1%}."
            )
            confidence = "средняя — Elo-модель"
            
            return {
                "selection": selection,
                "probability": probability,
                "odds": None,
                "fair_odds": fair_odds,
                "edge": None,
                "explanation": explanation,
                "confidence": confidence,
            }
    
    # ===== Приоритет 2: Рыночные кэфы (fallback) =====
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
            p = max(.05, min(.95, 0.85 * market_a + 0.15 * 0.5))
            odds = oa
            market_fav = market_a
        else:
            selection = f"Победа {b}"
            p = max(.05, min(.95, 0.85 * market_b + 0.15 * 0.5))
            odds = ob
            market_fav = market_b
        
        edge = p * odds - 1
        explanation = (
            f"Оценка на основе коэффициентов Pinnacle. "
            f"Рыночная вероятность {a} — {market_a:.1%}, {b} — {market_b:.1%}. "
            f"Модель выбирает фаворита: {selection.split('Победа ')[1]} "
            f"({market_fav:.1%} по рынку). "
            "Это не независимый сигнал — модель опирается на кэфы букмекера."
        )
        confidence = "низкая — нет независимой модели"
    else:
        p = 0.5
        odds = None
        edge = None
        selection = "Недостаточно данных для выбора"
        explanation = "Нет проверенных коэффициентов и статистики. Добавь коэффициенты."
        confidence = "очень низкая"
    
    return {
        "selection": selection,
        "probability": p,
        "odds": odds,
        "fair_odds": 1 / p,
        "edge": edge,
        "explanation": explanation,
        "confidence": confidence,
    }
