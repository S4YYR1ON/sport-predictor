def predict(sport, event):
    a = event.get("home", "Участник A")
    b = event.get("away", "Участник B")
    
    try: oa = float(event.get("odds_home")) if event.get("odds_home") else None
    except (TypeError, ValueError): oa = None
    try: ob = float(event.get("odds_away")) if event.get("odds_away") else None
    except (TypeError, ValueError): ob = None
    
    if oa and ob and oa > 1 and ob > 1:
        pa, pb = 1/oa, 1/ob
        market_a = pa / (pa + pb)
        market_b = 1 - market_a
        
        # ВЫБИРАЕМ ФАВОРИТА — того, у кого рыночная вероятность выше
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
        "fair_odds": 1/p,
        "edge": edge,
        "explanation": explanation,
        "confidence": confidence,
    }
