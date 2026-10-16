import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from db import (
    init_db, save_prediction, list_predictions,
    settle_prediction, summary, update_closing_odds, clv_summary,
)
from predictor import predict, find_elo_player
from sources import (
    get_events,
    source_status,
    get_elo_ratings,
    get_surface,
    get_all_betbetter_picks,
)
from stats import compute_match_stats

st.set_page_config(page_title="Sport Predictor", page_icon="📊", layout="wide")
init_db()

SPORTS = {
    "⚽ Футбол": "football",
    "🎾 Теннис": "tennis",
    "🛡 Dota 2": "dota2",
    "🎯 CS2": "cs2",
}


def format_time(raw):
    if not raw:
        return "неизвестно"
    try:
        clean = raw.split(".")[0].replace("Z", "")
        dt_utc = datetime.fromisoformat(clean)
        dt_msk = dt_utc + timedelta(hours=3)
        return dt_msk.strftime("%d.%m.%Y %H:%M") + " МСК"
    except Exception:
        return str(raw)


st.title("📊 Sport Predictor")
st.caption(
    "Личная спортивная аналитика · прогнозы и виртуальная статистика · "
    "без размещения реальных ставок"
)

with st.sidebar:
    st.header("Навигация")
    page = st.radio(
        "Раздел",
        [
            "Матчи и прогнозы",
            "Bet Better (ATP/WTA)",
            "Добавить матч вручную",
            "История прогнозов",
            "Виртуальный баланс",
            "Источники данных",
        ],
    )
    st.divider()
    st.caption("MVP: прогнозы экспериментальные. Никаких гарантий выигрыша.")


# ============================================================
# BET BETTER
# ============================================================
if page == "Bet Better (ATP/WTA)":
    st.subheader("📊 Прогнозы модели Bet Better")
    st.caption(
        "Независимая статистическая модель для тенниса ATP и WTA. "
        "Вероятности и справедливые кэфы — это оценка модели."
    )

    if st.button("Загрузить прогнозы", type="primary"):
        with st.spinner("Загружаю прогнозы модели…"):
            picks, error = get_all_betbetter_picks()
            st.session_state["bb_picks"] = picks
            st.session_state["bb_error"] = error

    if st.session_state.get("bb_error"):
        st.warning(st.session_state["bb_error"])

    picks = st.session_state.get("bb_picks", [])
    if not picks:
        st.info("Нажми «Загрузить прогнозы», чтобы получить список матчей.")
    else:
        CONF_RU = {
            "HIGH": "🟢 ВЫСОКАЯ", "LEAN": "🟡 УМЕРЕННАЯ",
            "LONG-SHOT": "🔴 РИСКОВАННАЯ", "LOCKED": "🔒 ЗАБЛОКИРОВАНО",
        }
        show_only_strong = st.checkbox(
            "Показывать только УМЕРЕННЫЕ и ВЫСОКИЕ (LEAN / HIGH)", value=False
        )
        show_locked = st.checkbox("Показывать заблокированные Moneyline", value=False)

        filtered = picks
        if show_only_strong:
            filtered = [p for p in filtered if p.get("confidence") in ("HIGH", "LEAN")]
        if not show_locked:
            filtered = [p for p in filtered if not p.get("locked")]

        st.success(f"Найдено прогнозов: {len(filtered)} (из {len(picks)})")

        for i, p in enumerate(filtered):
            with st.container(border=True):
                st.markdown(f"**{p['home']} — {p['away']}**")
                st.caption(f"🏆 {p['tour']} · Начало: {format_time(p.get('game_time', ''))}")
                sel = p.get("selection", "")
                conf_ru = CONF_RU.get(p.get("confidence", ""), p.get("confidence", ""))

                if p.get("locked"):
                    st.info("🔒 Moneyline откроется в момент начала матча.")
                    continue

                a, b, c = st.columns(3)
                a.metric("Прогноз модели", sel)
                b.metric(
                    "Вероятность",
                    f"{p['probability']}%" if p.get("probability") is not None else "—",
                )
                c.metric(
                    "Справедливый кэф",
                    f"{p['fair_odds']:.2f}" if p.get("fair_odds") else "—",
                )

                if "handicap" in sel.lower():
                    import re
                    m = re.search(r"([-+]?\d+\.?\d*)\s*games", sel)
                    line = m.group(1) if m else "?"
                    player = re.split(r"\s[-+]?\d", sel)[0].strip() if re.search(r"\s[-+]?\d", sel) else sel.split()[0]
                    st.info(
                        f"📌 **Что значит прогноз:** {player} должен выиграть "
                        f"с разницей в геймах больше {line}. "
                        f"Например, 6:2, 6:3 — зайдёт. А 6:4, 7:6 — не зайдёт."
                    )

                st.caption(f"Рынок: {p.get('market', '')}")
                st.caption(f"Уверенность модели: **{conf_ru}**")

                prob = p.get("probability")
                fair = p.get("fair_odds")
                if prob is not None and fair is not None:
                    with st.expander("🔍 Проверить value с кэфом BetBoom", expanded=False):
                        bookie_odd = st.number_input(
                            "Введи кэф BetBoom на этот исход",
                            min_value=1.01, max_value=100.0,
                            value=float(round(fair, 2)), step=0.01,
                            key=f"bb_odd_{i}",
                        )
                        if bookie_odd:
                            val = (prob / 100.0) * bookie_odd - 1
                            col1, col2 = st.columns(2)
                            col1.metric("Кэф BetBoom", f"{bookie_odd:.2f}")
                            col2.metric("Value", f"{val:+.1%}")
                            if val > 0.02:
                                st.success(f"✅ **VALUE есть!** {prob}% × {bookie_odd:.2f} = {1 + val:.3f}")
                            elif val > -0.02:
                                st.warning(f"⚠️ **На грани:** {val:+.1%}.")
                            else:
                                st.error(f"❌ **Value нет:** {val:+.1%}. Нужен кэф **{fair:.2f}**.")


# ============================================================
# МАТЧИ И ПРОГНОЗЫ
# ============================================================
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
            ["Все турниры", "Только топ (ATP/WTA)"],
        )
        tour_filter_key = "top" if tour_filter == "Только топ (ATP/WTA)" else "all"

    st.subheader(sport_label)

    if st.button("Загрузить доступные матчи", type="primary"):
        with st.spinner("Проверяю открытые источники…"):
            events, warning = get_events(
                sport, region=region_key, tour_filter=tour_filter_key
            )
        st.session_state["events"] = events
        st.session_state["events_sport"] = sport
        st.session_state["events_warning"] = warning

    if st.session_state.get("events_sport") == sport:
        if st.session_state.get("events_warning"):
            st.info(st.session_state["events_warning"])

        events = st.session_state.get("events", [])
        if not events:
            st.warning("Нет подтверждённых матчей. Можно добавить вручную.")
        else:
            for i, e in enumerate(events):
                with st.container(border=True):
                    st.markdown(f"**{e['home']} — {e['away']}**")
                    st.caption(
                        f"Начало: {format_time(e.get('start', ''))} · "
                        f"Источник: {e.get('source', 'не указан')}"
                    )

                    col1, col2 = st.columns([1, 3])
                    with col1:
                        if st.button("Анализировать", key=f"analyse_{sport}_{i}"):
                            with st.spinner("Анализирую (загружаю форму, H2H, Elo)…"):
                                league = (e.get("league_name") or "").upper()
                                tour_key = "wta" if "WTA" in league else "atp"

                                elo_dict, _ = get_elo_ratings(tour=tour_key)
                                if not (
                                    find_elo_player(elo_dict, e.get("home", ""))
                                    and find_elo_player(elo_dict, e.get("away", ""))
                                ):
                                    alt_tour = "wta" if tour_key == "atp" else "atp"
                                    alt_elo, _ = get_elo_ratings(tour=alt_tour)
                                    if (
                                        find_elo_player(alt_elo, e.get("home", ""))
                                        and find_elo_player(alt_elo, e.get("away", ""))
                                    ):
                                        elo_dict = alt_elo

                                surface = get_surface(e.get("league_name", ""))

                                match_stats = compute_match_stats(
                                    tour=tour_key,
                                    home_name=e.get("home", ""),
                                    away_name=e.get("away", ""),
                                    surface=surface,
                                    match_date=e.get("start"),
                                )

                                p = predict(
                                    sport, e, elo_dict=elo_dict,
                                    surface=surface, stats=match_stats,
                                )
                                pid = save_prediction(
                                    sport, f"{e['home']} — {e['away']}",
                                    p["selection"], p["probability"], p["odds"],
                                    p["explanation"], p["confidence"],
                                )
                                st.session_state["last_result"] = {
                                    "event": e, "p": p, "id": pid,
                                    "sport": sport, "match_stats": match_stats,
                                }
                            st.rerun()

                    with col2:
                        st.caption(
                            "Автоматические коэффициенты могут отсутствовать. "
                            "Проверяй состав, форму и статус матча."
                        )

                    if (
                        "last_result" in st.session_state
                        and st.session_state["last_result"]["sport"] == sport
                        and st.session_state["last_result"]["event"]["home"] == e["home"]
                        and st.session_state["last_result"]["event"]["away"] == e["away"]
                    ):
                        r = st.session_state["last_result"]
                        p = r["p"]
                        match_stats = r.get("match_stats")

                        st.divider()
                        st.markdown("### Результат анализа")
                        a, b, c = st.columns(3)
                        a.metric("Исход модели", p["selection"])
                        b.metric("Оценка вероятности", f"{p['probability']:.1%}")
                        c.metric("Справедливый коэффициент", f"{p['fair_odds']:.2f}")
                        st.write("**Надёжность данных:**", p["confidence"])
                        st.write("**Объяснение:**", p["explanation"])
                        st.caption(f"Сохранено как виртуальный прогноз №{r['id']}.")

                        # Дополнительные факторы
                        if match_stats:
                            with st.expander("📈 Дополнительные факторы", expanded=False):
                                col_h, col_a = st.columns(2)
                                with col_h:
                                    st.markdown(f"**{e['home']}**")
                                    fh = match_stats["home"].get("form") or {}
                                    if fh:
                                        st.write(f"Форма (10): **{fh['wins']}-{fh['losses']}** ({fh['win_rate']:.0%})")
                                    sh = match_stats["home"].get("surface") or {}
                                    if sh:
                                        st.write(f"Покрытие: **{sh['wins']}-{sh['matches'] - sh['wins']}** ({sh['win_rate']:.0%})")
                                    rh = match_stats["home"].get("rest")
                                    if rh is not None:
                                        st.write(f"Отдых: **{rh} дн.**")
                                        if rh > 30:
                                            st.caption(f"⚠️ Данные в базе устаревшие — последний матч более месяца назад.")
                                with col_a:
                                    st.markdown(f"**{e['away']}**")
                                    fa = match_stats["away"].get("form") or {}
                                    if fa:
                                        st.write(f"Форма (10): **{fa['wins']}-{fa['losses']}** ({fa['win_rate']:.0%})")
                                    sa = match_stats["away"].get("surface") or {}
                                    if sa:
                                        st.write(f"Покрытие: **{sa['wins']}-{sa['matches'] - sa['wins']}** ({sa['win_rate']:.0%})")
                                    ra = match_stats["away"].get("rest")
                                    if ra is not None:
                                        st.write(f"Отдых: **{ra} дн.**")
                                h2h = match_stats["home"].get("h2h") or {}
                                if h2h.get("total", 0) > 0:
                                    st.write(f"**H2H:** {h2h['a_wins']} — {h2h['b_wins']}")
                                else:
                                    st.caption("H2H: личных встреч не найдено")

                        # Value-калькулятор
                        prob_val = p["probability"]
                        fair_val = p["fair_odds"]
                        with st.expander("🔍 Проверить value с кэфом BetBoom", expanded=False):
                            bookie_odd = st.number_input(
                                "Введи кэф BetBoom на этот исход",
                                min_value=1.01, max_value=100.0,
                                value=float(round(fair_val, 2)), step=0.01,
                                key=f"mb_odd_{r['id']}",
                            )
                            if bookie_odd:
                                val = prob_val * bookie_odd - 1
                                c1, c2 = st.columns(2)
                                c1.metric("Кэф BetBoom", f"{bookie_odd:.2f}")
                                c2.metric("Value", f"{val:+.1%}")
                                if val > 0.02:
                                    st.success(f"✅ **VALUE есть!** {prob_val:.1%} × {bookie_odd:.2f} = {1 + val:.3f}")
                                elif val > -0.02:
                                    st.warning(f"⚠️ **На грани:** {val:+.1%}.")
                                else:
                                    st.error(f"❌ **Value нет:** {val:+.1%}. Нужен кэф **{fair_val:.2f}**.")


# ============================================================
# ДОБАВИТЬ ВРУЧНУЮ
# ============================================================
elif page == "Добавить матч вручную":
    st.subheader("Добавить матч")
    with st.form("manual_match"):
        sport_label = st.selectbox("Спорт", list(SPORTS), key="manual_sport")
        c1, c2 = st.columns(2)
        a = c1.text_input("Участник A")
        b = c2.text_input("Участник B")
        c3, c4 = st.columns(2)
        oa = c3.number_input("Коэф. на A", min_value=1.01, value=1.80, step=0.05)
        ob = c4.number_input("Коэф. на B", min_value=1.01, value=2.10, step=0.05)
        submitted = st.form_submit_button("Рассчитать и сохранить", type="primary")

    if submitted:
        if not a.strip() or not b.strip():
            st.error("Введи названия обоих участников.")
        else:
            sport = SPORTS[sport_label]
            e = {"home": a.strip(), "away": b.strip(),
                 "odds_home": oa, "odds_away": ob, "manual": True}
            p = predict(sport, e)
            pid = save_prediction(
                sport, f"{a} — {b}", p["selection"], p["probability"],
                p["odds"], p["explanation"], p["confidence"],
            )
            st.success(f"Сохранено как прогноз №{pid}")
            x, y, z = st.columns(3)
            x.metric("Исход модели", p["selection"])
            y.metric("Вероятность", f"{p['probability']:.1%}")
            z.metric("Справедливый коэффициент", f"{p['fair_odds']:.2f}")
            st.warning(p["explanation"])


# ============================================================
# ИСТОРИЯ
# ============================================================
elif page == "История прогнозов":
    st.subheader("История прогнозов")
    rows = list_predictions(100)
    if not rows:
        st.info("Прогнозов пока нет.")
    else:
        df = pd.DataFrame(rows)
        df = df.rename(columns={
            "id": "ID", "sport": "Спорт", "event": "Матч",
            "selection": "Исход", "probability": "Вероятность",
            "odds": "Коэф", "closing_odds": "Closing", "clv": "CLV",
            "status": "Статус", "profit": "Вирт. P/L", "created_at": "Создан",
        })
        keep = [c for c in [
            "ID", "Спорт", "Матч", "Исход", "Вероятность",
            "Коэф", "Closing", "CLV", "Статус", "Вирт. P/L", "Создан",
        ] if c in df.columns]
        st.dataframe(df[keep], use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("📊 CLV-трекер")
        st.caption(
            "CLV — разница между твоим кэфом и closing line Pinnacle. "
            "Стабильно > 0 = преимущество есть."
        )
        with st.form("clv_form"):
            clv_pid = st.number_input("ID прогноза", min_value=1, step=1, key="clv_pid")
            clv_odd = st.number_input(
                "Closing line Pinnacle",
                min_value=1.01, value=1.50, step=0.01, key="clv_odd",
            )
            if st.form_submit_button("Сохранить closing odds и посчитать CLV"):
                if update_closing_odds(int(clv_pid), float(clv_odd)):
                    st.success("CLV сохранён.")
                    st.rerun()
                else:
                    st.error("Не найден прогноз с таким ID.")

        st.divider()
        with st.form("settle"):
            pid = st.number_input("ID прогноза для закрытия", min_value=1, step=1)
            result = st.selectbox(
                "Фактический результат", ["won", "lost", "void"],
                format_func=lambda x: {
                    "won": "Выиграл", "lost": "Проиграл", "void": "Возврат",
                }[x],
            )
            if st.form_submit_button("Закрыть прогноз"):
                if settle_prediction(int(pid), result):
                    st.success("Прогноз закрыт. Обнови страницу.")
                else:
                    st.error("Не найден открытый прогноз с таким ID.")


# ============================================================
# БАЛАНС
# ============================================================
elif page == "Виртуальный баланс":
    s = summary()
    a, b, c, d = st.columns(4)
    a.metric("Закрыто прогнозов", s["settled"])
    b.metric("Победы", s["won"])
    c.metric("Поражения", s["lost"])
    d.metric("Виртуальный P/L", f"{s['profit']:+.2f} ед.")
    st.info("Ставка — 1 виртуальная единица. Это не реальные деньги.")

    st.divider()
    st.subheader("📊 CLV (Closing Line Value)")
    clv = clv_summary()
    if clv["count"] == 0:
        st.info("CLV пока не посчитан. Введи closing odds в «Истории прогнозов».")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Прогнозов с CLV", clv["count"])
        c2.metric("Средний CLV", f"{clv['avg_clv']:+.2%}")
        c3.metric("CLV > 0", f"{clv['positive']} из {clv['count']}")
        if clv["avg_clv"] > 0:
            st.success("✅ Средний CLV положительный — модель ставит лучше closing line.")
        else:
            st.warning("⚠️ Средний CLV отрицательный — ставки невыгодные.")


# ============================================================
# ИСТОЧНИКИ
# ============================================================
elif page == "Источники данных":
    st.subheader("Доступность источников")
    for name, status in source_status().items():
        st.write(f"**{name}:** {status}")
    st.warning(
        "Прогнозы: Elo Tennis Abstract + калибровка + форма + H2H + "
        "отдых + покрытие. Травмы и составы не учитываются автоматически."
    )
    st.write(
        "BetBoom не подключён: нет публичного API. "
        "Не вводи логины, пароли, cookies."
    )

st.divider()
st.caption("Следующий этап: травмы, погода, CLV-аналитика.")
