import streamlit as st
import pandas as pd
from db import init_db, save_prediction, list_predictions, settle_prediction, summary
from predictor import predict
from sources import get_events, source_status
from datetime import datetime

def format_time(raw):
    """Превращает '2026-10-17T08:30:00.0000000Z' в '17.10.2026 08:30'."""
    if not raw:
        return "неизвестно"
    try:
        # Отрезаем лишние нули после секунд
        clean = raw.split(".")[0].replace("Z", "")
        dt = datetime.fromisoformat(clean)
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(raw)
        
st.set_page_config(page_title="Sport Predictor", page_icon="📊", layout="wide")
init_db()
SPORTS = {
    "⚽ Футбол": "football",
    "🏀 Баскетбол": "basketball",
    "🎾 Теннис": "tennis",
    "🛡 Dota 2": "dota2",
    "🎯 CS2": "cs2",
}
st.title("📊 Sport Predictor")
st.caption("Личная спортивная аналитика · прогнозы и виртуальная статистика · без размещения реальных ставок")

with st.sidebar:
    st.header("Навигация")
    page = st.radio("Раздел", ["Матчи и прогнозы", "Bet Better (ATP/WTA)", "Добавить матч вручную", "История прогнозов", "Виртуальный баланс", "Источники данных"])
    st.divider()
    st.caption("MVP: прогнозы экспериментальные. Никаких гарантий выигрыша.")
if page == "Bet Better (ATP/WTA)":
    st.subheader("📊 Прогнозы модели Bet Better")
    st.caption("Независимая статистическая модель для тенниса ATP и WTA. "
               "Вероятности и справедливые кэфы — это оценка модели, а не коэффициенты букмекеров.")

    if st.button("Загрузить прогнозы", type="primary"):
        with st.spinner("Загружаю прогнозы и сопоставляю с Pinnacle…"):
            from sources import get_betbetter_with_value
            picks, error = get_betbetter_with_value()
            st.session_state["bb_picks"] = picks
            st.session_state["bb_error"] = error

    if st.session_state.get("bb_error"):
        st.warning(st.session_state["bb_error"])

    picks = st.session_state.get("bb_picks", [])

    if not picks:
        st.info("Нажми «Загрузить прогнозы», чтобы получить список матчей.")
    else:
        # Фильтр по уверенности
        show_only_strong = st.checkbox(
            "Показывать только УМЕРЕННЫЕ и ВЫСОКИЕ (LEAN / HIGH)",
            value=False
        )
        show_only_value = st.checkbox(
            "Показывать только матчи с потенциальным VALUE",
            value=False
        )

        # Перевод уверенности на русский
        CONF_RU = {
            "HIGH": "🟢 ВЫСОКАЯ",
            "LEAN": "🟡 УМЕРЕННАЯ",
            "LONG-SHOT": "🔴 РИСКОВАННАЯ",
        }

        # Фильтрация
        filtered = picks
        if show_only_strong:
            filtered = [p for p in filtered if p.get("confidence") in ("HIGH", "LEAN")]
        if show_only_value:
            filtered = [p for p in filtered if (p.get("value") or 0) > 0]

        st.success(f"Найдено прогнозов: {len(filtered)} (из {len(picks)})")

        for i, p in enumerate(filtered):
            with st.container(border=True):
                st.markdown(f"**{p['home']} — {p['away']}**")
                st.caption(f"🏆 {p['tour']} · Начало: {format_time(p.get('game_time', ''))}")
                st.caption(f"Рынок: {p.get('market', '')}")

                a, b, c = st.columns(3)
                a.metric("Прогноз модели", p.get("selection", ""))
                b.metric("Вероятность", f"{p['probability']}%" if p.get("probability") is not None else "—")
                c.metric("Справедливый кэф", f"{p['fair_odds']:.2f}" if p.get("fair_odds") else "—")

                conf_ru = CONF_RU.get(p.get("confidence", ""), p.get("confidence", ""))
                st.caption(f"Уверенность модели: **{conf_ru}**")

                # Коэффициент Pinnacle и value
                if p.get("match_found"):
                    if p.get("market_odd"):
                        odd = p["market_odd"]
                        val = p.get("value")
                        col1, col2 = st.columns(2)
                        col1.metric("Кэф Pinnacle", f"{odd:.2f}")
                        if val is not None:
                            if val > 0:
                                col2.metric("VALUE", f"{val:+.1%}", delta_color="normal")
                                st.success(f"✅ Потенциальный VALUE: вероятность модели {p['probability']}% × кэф {odd:.2f} = {1+val:.3f}")
                            else:
                                col2.metric("VALUE", f"{val:+.1%}", delta_color="inverse")
                                st.info(f"❌ Value нет: вероятность модели {p['probability']}% × кэф {odd:.2f} = {1+val:.3f}")
                    else:
                        st.caption("⚠️ Матч найден в Pinnacle, но подходящий спред или moneyline отсутствует.")
                else:
                    st.caption("⚠️ Матч не найден в Pinnacle — сравнить кэфы не удалось.")

                if p.get("verdict"):
                    with st.expander("Объяснение модели"):
                        st.write(p["verdict"])

elif page == "Матчи и прогнозы":
    sport_label = st.selectbox("Выбери спорт", list(SPORTS))
    sport = SPORTS[sport_label]
    st.subheader(sport_label)
    
    if st.button("Загрузить доступные матчи", type="primary"):
        with st.spinner("Проверяю открытые источники…"):
            events, warning = get_events(sport)
        st.session_state["events"] = events
        st.session_state["events_sport"] = sport
        st.session_state["events_warning"] = warning
    if st.session_state.get("events_sport") == sport:
        if st.session_state.get("events_warning"):
            st.info(st.session_state["events_warning"])
        events = st.session_state.get("events", [])
        if not events:
            st.warning("Сейчас нет подтверждённых матчей для отображения. Можно добавить матч вручную.")
        else:
            for i, e in enumerate(events):
                with st.container(border=True):
                    st.markdown(f"**{e['home']} — {e['away']}**")
                    st.caption(f"Начало: {e.get('start','неизвестно')} · Источник: {e.get('source','не указан')}")
                    
                    # Bet Better
                    if e.get("bb_home_prob") or e.get("bb_away_prob"):
                        st.caption("📊 **Модель Bet Better:**")
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if e.get("bb_home_prob"):
                                st.metric(f"Вероятность {e['home']}", f"{e['bb_home_prob']}%", 
                                         f"fair odds {e['bb_home_fair']}")
                                st.caption(f"Уверенность: {e['bb_home_conf']}")
                        with col_b:
                            if e.get("bb_away_prob"):
                                st.metric(f"Вероятность {e['away']}", f"{e['bb_away_prob']}%", 
                                         f"fair odds {e['bb_away_fair']}")
                                st.caption(f"Уверенность: {e['bb_away_conf']}")
                    else:
                        st.caption("📊 *Bet Better: матч не найден в базе модели*")
                        
                    col1,col2=st.columns([1,3])
                    with col1:
                        if st.button("Анализировать", key=f"analyse_{sport}_{i}"):
                            with st.spinner("Анализирую и сохраняю..."):
                                odds_home, odds_away = None, None
                                odds_error = None
                                
                                if e.get("has_market") and e.get("match_id"):
                                    odds_result, odds_error = get_match_odds(e["match_id"])
                                    if odds_result:
                                        odds_home = odds_result.get("home")
                                        odds_away = odds_result.get("away")
                                        e["odds_home"] = odds_home
                                        e["odds_away"] = odds_away
                                
                                p = predict(sport, e)
                                pid = save_prediction(sport, f"{e['home']} — {e['away']}", p["selection"], p["probability"], p["odds"], p["explanation"], p["confidence"])
                                st.session_state["last_result"] = {"event": e, "p": p, "id": pid, "sport": sport, "odds_error": odds_error}
                            st.rerun()
                    with col2:
                        st.caption("Автоматические коэффициенты могут отсутствовать. Не делай выводов без проверки состава, формы и статуса матча.")
                    
                    # Вывод результата прямо внутри карточки
                    if ("last_result" in st.session_state and 
                        st.session_state["last_result"]["sport"] == sport and
                        st.session_state["last_result"]["event"]["home"] == e["home"] and
                        st.session_state["last_result"]["event"]["away"] == e["away"]):
                        r = st.session_state["last_result"]
                        p = r["p"]
                        st.divider()
                        st.markdown("### Результат анализа")
                        a,b,c = st.columns(3)
                        a.metric("Исход модели", p["selection"])
                        b.metric("Оценка вероятности", f"{p['probability']:.1%}")
                        c.metric("Справедливый коэффициент", f"{p['fair_odds']:.2f}")
                        st.write("**Надёжность данных:**", p["confidence"])
                        st.write("**Объяснение:**", p["explanation"])
                        st.caption(f"Сохранено как виртуальный прогноз №{r['id']}.")
                        if r.get("odds_error"):
                            st.warning(f"⚠️ Коэффициенты не получены: {r['odds_error']}")
    

elif page == "Добавить матч вручную":
    st.subheader("Добавить матч")
    with st.form("manual_match"):
        sport_label=st.selectbox("Спорт",list(SPORTS), key="manual_sport")
        c1,c2=st.columns(2)
        a=c1.text_input("Участник / команда A")
        b=c2.text_input("Участник / команда B")
        c3,c4=st.columns(2)
        oa=c3.number_input("Коэффициент на A",min_value=1.01,value=1.80,step=0.05)
        ob=c4.number_input("Коэффициент на B",min_value=1.01,value=2.10,step=0.05)
        submitted=st.form_submit_button("Рассчитать и сохранить",type="primary")
    if submitted:
        if not a.strip() or not b.strip():
            st.error("Введи названия обоих участников.")
        else:
            sport=SPORTS[sport_label]
            e={"home":a.strip(),"away":b.strip(),"odds_home":oa,"odds_away":ob,"manual":True}
            p=predict(sport,e)
            pid=save_prediction(sport,f"{a} — {b}",p["selection"],p["probability"],p["odds"],p["explanation"],p["confidence"])
            st.success(f"Сохранено как виртуальный прогноз №{pid}")
            x,y,z=st.columns(3)
            x.metric("Исход модели",p["selection"])
            y.metric("Вероятность",f"{p['probability']:.1%}")
            z.metric("Справедливый коэффициент",f"{p['fair_odds']:.2f}")
            st.write("**Оценка преимущества:**", "не рассчитана" if p["edge"] is None else f"{p['edge']:+.1%}")
            st.warning(p["explanation"])

elif page == "История прогнозов":
    st.subheader("История прогнозов")
    rows=list_predictions(100)
    if not rows:
        st.info("Прогнозов пока нет.")
    else:
        df=pd.DataFrame(rows)
        df=df.rename(columns={"id":"ID","sport":"Спорт","event":"Матч","selection":"Исход","probability":"Вероятность","odds":"Коэффициент","status":"Статус","profit":"Вирт. P/L","created_at":"Создан"})
        keep=[c for c in ["ID","Спорт","Матч","Исход","Вероятность","Коэффициент","Статус","Вирт. P/L","Создан"] if c in df.columns]
        st.dataframe(df[keep],use_container_width=True,hide_index=True)
        st.caption("Вероятность — экспериментальная оценка. Пока модель не получает полную статистику формы автоматически.")
        with st.form("settle"):
            pid=st.number_input("ID прогноза для закрытия",min_value=1,step=1)
            result=st.selectbox("Фактический результат",["won","lost","void"],format_func=lambda x:{"won":"Выиграл","lost":"Проиграл","void":"Возврат / отмена"}[x])
            if st.form_submit_button("Закрыть прогноз"):
                if settle_prediction(int(pid),result):
                    st.success("Виртуальный прогноз закрыт. Обнови страницу раздела.")
                else:
                    st.error("Не найден открытый прогноз с таким ID.")

elif page == "Виртуальный баланс":
    s=summary()
    a,b,c,d=st.columns(4)
    a.metric("Закрыто прогнозов",s["settled"])
    b.metric("Победы",s["won"])
    c.metric("Поражения",s["lost"])
    d.metric("Виртуальный P/L",f"{s['profit']:+.2f} ед.")
    st.info("Для каждого прогноза считается условная ставка в 1 виртуальную единицу. Это не реальные деньги.")

elif page == "Источники данных":
    st.subheader("Доступность источников")
    for name,status in source_status().items():
        st.write(f"**{name}:** {status}")
    st.warning("В этой версии нет полного автоматического сбора последних пяти матчей, травм, составов и расширенной статистики. Не подменяем отсутствующие данные выдуманными.")
    st.write("BetBoom не подключён: не подтверждён официальный разрешённый способ автоматического получения коэффициентов. Не вводи здесь логин, пароль, cookies или коды подтверждения.")

st.divider()
st.caption("Следующий этап: подключить проверенные источники истории матчей, составов и статистики, затем проверить качество модели на прошлых матчах.")
