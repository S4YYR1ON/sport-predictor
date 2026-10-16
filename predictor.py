import pandas as pd

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
    
def predict(sport, event, elo_dict=None, surface="hard"):
    a = event.get("home", "Участник A")
    b = event.get("away", "Участник B")
    
    # ===== Приоритет 1: Elo-модель =====
    if elo_dict:
        elo_a = find_elo_player(elo_dict, a)
        elo_b = find_elo_player(elo_dict, b)
        if elo_a and elo_b:
            # Выбираем поле Elo в зависимости от покрытия
            surface_key = {
                "hard": "hElo",
                "clay": "cElo",
                "grass": "gElo",
            }.get(surface, "elo")
            
            elo_a_val = elo_a.get(surface_key) if isinstance(elo_a, dict) else elo_a
            elo_b_val = elo_b.get(surface_key) if isinstance(elo_b, dict) else elo_b
            
            # Если Elo по покрытию нет — падаем на общий Elo
            if not elo_a_val or not elo_b_val or pd.isna(elo_a_val) or pd.isna(elo_b_val):
                elo_a_val = elo_a.get("elo") if isinstance(elo_a, dict) else elo_a
                elo_b_val = elo_b.get("elo") if isinstance(elo_b, dict) else elo_b
                surface_key = "elo"
            
            if elo_a_val and elo_b_val:
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
                surface_ru = {"hard": "хард", "clay": "грунт", "grass": "трава"}.get(surface, "хард")
                
                explanation = (
                    f"Прогноз на основе Elo-рейтингов Tennis Abstract ({surface_ru}). "
                    f"{a} ({elo_a_val:.0f}) vs {b} ({elo_b_val:.0f}). "
                    f"Вероятность победы {fav} — {probability:.1%}, "
                    f"{dog} — {1-probability:.1%}."
                )
                confidence = f"средняя — Elo-модель ({surface_ru})"
                
                return {
                    "selection": selection,
                    "probability": probability,
                    "odds": None,
                    "fair_odds": fair_odds,
                    "edge": None,
                    "explanation": explanation,
                    "confidence": confidence,
                }
    
    # ... остальной код fallback без изменений ...
