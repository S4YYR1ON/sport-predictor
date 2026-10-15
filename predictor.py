def predict(sport,event):
    a=event.get("home","Участник A"); b=event.get("away","Участник B")
    try: oa=float(event.get("odds_home")) if event.get("odds_home") else None
    except (TypeError,ValueError): oa=None
    try: ob=float(event.get("odds_away")) if event.get("odds_away") else None
    except (TypeError,ValueError): ob=None
    if oa and ob and oa>1 and ob>1:
        pa,pb=1/oa,1/ob
        market=pa/(pa+pb)
        p=max(.05,min(.95,.85*market+.15*.5))
        selection=f"Победа {a}"
        odds=oa
        edge=p*odds-1
        explanation=(f"Оценка в основном основана на введённых коэффициентах: рыночная вероятность A около {market:.1%}. "
        "Последние пять матчей, составы и травмы автоматически не подтверждены. Это не независимый сигнал; положительное преимущество не доказано.")
        confidence="низкая — нет подтверждённой статистики формы"
    else:
        p=.5; odds=None; edge=None
        selection="Недостаточно данных для выбора"
        explanation="Нет проверенных коэффициентов и статистики. Не выбираю исход наугад; добавь коэффициенты и проверь данные участников."
        confidence="очень низкая"
    return {"selection":selection,"probability":p,"odds":odds,"fair_odds":1/p,"edge":edge,
            "explanation":explanation,"confidence":confidence}
