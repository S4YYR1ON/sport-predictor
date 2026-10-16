import streamlit as st
import pandas as pd
from db import init_db, save_prediction, list_predictions, settle_prediction, summary
from predictor import predict
from sources import get_events, source_status, get_elo_ratings

from datetime import datetime, timedelta

def format_time(raw):
    """Превращает '2026-10-17T08:30:00.0000000Z' (UTC) в '17.10.2026 11:30' (МСК)."""
    if not raw:
        return "неизвестно"
    try:
        clean = raw.split(".")[0].replace("Z", "")
        dt_utc = datetime.fromisoformat(clean)
        dt_msk = dt_utc + timedelta(hours=3)
        return dt_msk.strftime("%d.%m.%Y %H:%M") + " МСК"
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
        show_locked = st.checkbox(
            "Показывать заблокированные Moneyline (откроются в момент матча)",
            value=False
        )

        # Перевод уверенности на русский
        CONF_RU = {
            "HIGH": "🟢 ВЫСОКАЯ",
            "LEAN": "🟡 УМЕРЕННАЯ",
            "LONG-SHOT": "🔴 РИСКОВАННАЯ",
            "LOCKED": "🔒 ЗАБЛОКИРОВАНО (откроется в момент матча)",
        }

        # Фильтрация
        filtered = picks
        if show_only_strong:
            filtered = [p for p in filtered if p.get("confidence") in ("HIGH", "LEAN")]
        if show_only_value:
            filtered = [p for p in filtered if (p.get("value") or 0) > 0]
        if not show_locked:
            filtered = [p for p in filtered if not p.get("locked")]

        st.success(f"Найдено прогнозов: {len(filtered)} (из {len(picks)})")

        for i, p in enumerate(filtered):
            with st.container(border=True):
                st.markdown(f"**{p['home']} — {p['away']}**")
                st.caption(f"🏆 {p['tour']} · Начало: {format_time(p.get('game_time', ''))}")

                # === МЕТРИКИ: прогноз, вероятность, fair odds ===
                sel = p.get("selection", "")
                a, b, c = st.columns(3)
                a.metric("Прогноз модели", sel)
                b.metric("Вероятность", f"{p['probability']}%" if p.get("probability") is not None else "—")
                c.metric("Справедливый кэф", f"{p['fair_odds']:.2f}" if p.get("fair_odds") else "—")

                # === Пояснение гандикапа простыми словами ===
                if "handicap" in sel.lower():
                    import re
                    m = re.search(r"([-+]?\d+\.?\d*)\s*games", sel)
                    line = m.group(1) if m else "?"
                    # Берём имя игрока до пробела с числом
                    player = re.split(r"\s[-+]?\d", sel)[0].strip() if re.search(r"\s[-+]?\d", sel) else sel.split()[0]
                    st.info(f"📌 **Что значит прогноз:** {player} должен выиграть матч "
                            f"с разницей в геймах больше {line}. То есть, например, 6:2, 6:3 "
                            f"(разница +7) — зайдёт. А 6:4, 7:6 (разница +3) — не зайдёт.")

                st.caption(f"Рынок: {p.get('market', '')} · Полная формулировка: {sel}")

                # === Уверенность модели ===
                conf_ru = CONF_RU.get(p.get("confidence", ""), p.get("confidence", ""))
                st.caption(f"Уверенность модели: **{conf_ru}**")
                
                # === Проверка value с кэфом букмекера (ввод вручную) ===
                prob = p.get("probability")
                fair = p.get("fair_odds")
                if prob is not None and fair is not None:
                    with st.expander("🔍 Проверить value с кэфом букмекера (BetBoom и др.)", expanded=False):
                        bookie_odd = st.number_input(
                            "Введи кэф букмекера на этот исход",
                            min_value=1.01,
                            max_value=100.0,
                            value=float(round(fair, 2)),
                            step=0.01,
                            key=f"bookie_odd_{i}"
                        )
                        if bookie_odd:
                            val = (prob / 100.0) * bookie_odd - 1
                            col1, col2 = st.columns(2)
                            col1.metric("Кэф букмекера", f"{bookie_odd:.2f}")
                            col2.metric("Value", f"{val:+.1%}")
                            
                            if val > 0.02:
                                st.success(
                                    f"✅ **VALUE есть!** Вероятность модели {prob}% × кэф {bookie_odd:.2f} = "
                                    f"{1+val:.3f}. На длинной дистанции это плюс."
                                )
                            elif val > -0.02:
                                st.warning(
                                    f"⚠️ **Value на грани:** {val:+.1%}. "
                                    f"Ставка почти нейтральная — маржа букмекера съедает весь запас."
                                )
                            else:
                                st.error(
                                    f"❌ **Value нет:** {val:+.1%}. "
                                    f"Для положительного value нужен кэф **минимум {fair:.2f}**, "
                                    f"а букмекер даёт только {bookie_odd:.2f}. Ставить невыгодно."
                                )
                            
                            st.caption(
                                f"Справедливый кэф модели: **{fair:.2f}** · "
                                f"Минимальный кэф для value: **{fair:.2f}** · "
                                f"Текущий кэф букмекера: **{bookie_odd:.2f}**"
                            )
                            
                # === Сопоставление с Pinnacle и расчёт VALUE ===
                if p.get("match_found"):
                    if p.get("market_odd"):
                        odd = p["market_odd"]
                        val = p.get("value")
                        col1, col2 = st.columns(2)
                        col1.metric("Кэф Pinnacle", f"{odd:.2f}")
                        if val is not None:
                            if val > 0:
                                col2.metric("VALUE", f"{val:+.1%}")
                                st.success(f"✅ Потенциальный VALUE: {p['probability']}% × {odd:.2f} = {1+val:.3f}")
                            else:
                                col2.metric("VALUE", f"{val:+.1%}")
                                st.info(f"❌ Value нет: {p['probability']}% × {odd:.2f} = {1+val:.3f}")
                    else:
                        st.caption("⚠️ Матч найден в Pinnacle, но подходящий спред отсутствует.")
                else:
                    st.caption("⚠️ Матч не найден в Pinnacle — сравнить кэфы не удалось.")

                # === Русское объяснение модели ===
                game_date = format_time(p.get("game_time", ""))
                if p.get("locked"):
                    explanation = (
                        f"Прогноз Moneyline (чистая победа) по этому матчу "
                        f"будет открыт Bet Better в момент начала матча "
                        f"({game_date}). До этого момента модель не публикует "
                        f"вероятность и справедливый коэффициент для этого исхода."
                    )
                else:
                    fair_str = f"{p['fair_odds']:.2f}" if p.get("fair_odds") else "—"
                    prob_str = f"{p['probability']}%" if p.get("probability") is not None else "—"
                    explanation = (
                        f"По оценке модели Bet Better на {game_date} исход "
                        f"«{sel}» имеет вероятность {prob_str}, что соответствует "
                        f"справедливому коэффициенту {fair_str}. "
                        f"Уверенность модели: {conf_ru}."
                    )
                with st.expander("Объяснение модели (на русском)"):
                    st.write(explanation)
                    if p.get("verdict"):
                        st.caption("Оригинал от Bet Better:")
                        st.caption(p["verdict"])

elif page == "Матчи и прогнозы":
    sport_label = st.selectbox("Выбери спорт", list(SPORTS))
    sport = SPORTS[sport_label]
    
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        region = st.selectbox("Регион", ["Все", "Европа"])
        region_key = "europe" if region == "Европа" else "all"
    with col_f2:
        tour_filter = st.selectbox(
            "Фильтр турниров",
            ["Все турниры", "Только топ (ATP/WTA 250+, ТБШ)"]
        )
        tour_filter_key = "top" if tour_filter == "Только топ (ATP/WTA 250+, ТБШ)" else "all"
    
    st.subheader(sport_label)
    
    if st.button("Загрузить доступные матчи", type="primary"):
        with st.spinner("Проверяю открытые источники…"):
            events, warning = get_events(sport, region=region_key, tour_filter=tour_filter_key)
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
                    st.caption(f"Начало: {format_time(e.get('start', ''))} · Источник: {e.get('source', 'не указан')}")
                        
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
                                
                                # Определяем тур по названию лиги
                                league = (e.get("league_name") or "").upper()
                                if "WTA" in league:
                                    tour_key = "wta"
                                elif "ATP" in league:
                                    tour_key = "atp"
                                else:
                                    tour_key = "atp"  # fallback
                                
                                elo_dict, _ = get_elo_ratings(tour=tour_key)
                                
                                # Если игрок не найден в основном туре — пробуем другой тур
                                from sources import find_elo_player
                                if not (find_elo_player(elo_dict, e.get("home", "")) and find_elo_player(elo_dict, e.get("away", ""))):
                                    alt_tour = "wta" if tour_key == "atp" else "atp"
                                    alt_elo, _ = get_elo_ratings(tour=alt_tour)
                                    # Если в альтернативном туре нашлись оба игрока — используем его
                                    if (find_elo_player(alt_elo, e.get("home", "")) and find_elo_player(alt_elo, e.get("away", ""))):
                                        elo_dict = alt_elo
                                
                                p = predict(sport, e, elo_dict=elo_dict)
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
                        prob = r["p"]["probability"]
                        fair = r["p"]["fair_odds"]
                        with st.expander("🔍 Проверить value с кэфом BetBoom", expanded=False):
                            bookie_odd = st.number_input(
                                "Введи кэф BetBoom на этот исход",
                                min_value=1.01, max_value=100.0,
                                value=float(round(fair, 2)), step=0.01,
                                key=f"bookie_odd_{r['id']}"
                            )
                            if bookie_odd:
                                val = prob * bookie_odd - 1
                                col1, col2 = st.columns(2)
                                col1.metric("Кэф BetBoom", f"{bookie_odd:.2f}")
                                col2.metric("Value", f"{val:+.1%}")
                                if val > 0.02:
                                    st.success(f"✅ **VALUE есть!** {prob:.1%} × {bookie_odd:.2f} = {1+val:.3f}")
                                elif val > -0.02:
                                    st.warning(f"⚠️ **На грани:** {val:+.1%}. Лучше пропустить.")
                                else:
                                    st.error(f"❌ **Value нет:** {val:+.1%}. Нужен кэф минимум **{fair:.2f}**.")
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
