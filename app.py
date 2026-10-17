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
)
from stats import compute_match_stats

st.set_page_config(page_title="Sport Predictor", page_icon="📊", layout="wide")
# --- СТИЛИЗАЦИЯ НАВИГАЦИИ ---
# --- СТИЛИЗАЦИЯ КНОПОК НАВИГАЦИИ ---
st.markdown("""
<style>
    /* 1. Настраиваем все кнопки в сайдбаре */
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button {
        justify-content: flex-start !important; /* Выравниваем текст влево */
        padding-left: 15px !important; /* Отступ слева */
        border-radius: 6px !important; /* Слегка скругляем углы */
        font-weight: 600 !important;
        font-size: 1.05rem !important;
        width: 100% !important;
        border: 1px solid #333 !important;
        transition: all 0.2s ease !important;
    }

    /* 2. Неактивные кнопки (серые) */
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"] {
        background-color: transparent !important;
        color: #FAFAFA !important;
        border-color: #444 !important;
    }

    /* 3. Эффект при наведении на неактивную кнопку */
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"]:hover {
        background-color: #262730 !important;
        border-color: #1f77b4 !important;
        color: #1f77b4 !important;
    }

    /* 4. Активная кнопка (синяя плашка) */
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] {
        background-color: #1f77b4 !important;
        color: #FFFFFF !important;
        border: 1px solid #1f77b4 !important;
    }
    
    /* 5. Убираем стандартный фокус (обводку) при клике */
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button:focus {
        box-shadow: none !important;
        outline: none !important;
    }
</style>
""", unsafe_allow_html=True)

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
    
    # Инициализируем текущую страницу в памяти, если ее нет
    if "current_page" not in st.session_state:
        st.session_state.current_page = "Матчи и прогнозы"

    # Функция для отрисовки красивой кнопки навигации
    def nav_button(label):
        # Если это текущая страница — делаем кнопку синей (primary), иначе обычной (secondary)
        btn_type = "primary" if st.session_state.current_page == label else "secondary"
        if st.button(label, use_container_width=True, type=btn_type):
            st.session_state.current_page = label
            st.rerun()

    # Рисуем кнопки
    nav_button("Матчи и прогнозы")
    nav_button("Добавить матч вручную")
    nav_button("История прогнозов")
    nav_button("Виртуальный баланс")
    nav_button("Источники данных")

    # Записываем выбранную страницу в переменную
    page = st.session_state.current_page

# МАТЧИ И ПРОГНОЗЫ
# ============================================================
if page == "Матчи и прогнозы":
    sport_label = st.selectbox("Выбери спорт", list(SPORTS))
    sport = SPORTS[sport_label]

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        region = st.selectbox("Регион", ["Все", "Европа"])
        region_key = "europe" if region == "Европа" else "all"
    with col_f2:
        tour_filter = st.selectbox(
            "Фильтр турниров",
            ["Все турниры", "Только топ (ATP/WTA)", "Только ITF/Challenger"],
        )
        if tour_filter == "Только топ (ATP/WTA)":
            tour_filter_key = "top"
        elif tour_filter == "Только ITF/Challenger":
            tour_filter_key = "itf"
        else:
            tour_filter_key = "all"

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
                        
                        # УМНОЕ РАЗДЕЛЕНИЕ СТАТУСОВ
                        confidence_text = p.get("confidence", "")
                        if "Pinnacle" in confidence_text or "нет независимой модели" in confidence_text:
                            st.info("ℹ️ **Оценка рынка (Pinnacle):** Нет Elo-рейтинга. Используются котировки букмекера. (Поиск value по отклонению BetBoom).")
                        else:
                            st.success("✅ **Независимый прогноз (Модель Elo):** Вероятность рассчитана на основе рейтингов, формы и ML-корректировок.")
                            
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
                                
                                # === ДОМАШНИЙ ИГРОК ===
                                with col_h:
                                    st.markdown(f"**{e['home']}**")
                                    
                                    # Форма
                                    fh = match_stats["home"].get("form")
                                    if fh and fh.get("win_rate") is not None and not fh.get("insufficient_data"):
                                        st.write(f"Форма (10): **{fh['wins']}-{fh['losses']}** ({fh['win_rate']:.0%})")
                                    else:
                                        st.caption("Форма: нет данных")
                                        
                                    # Покрытие
                                    sh = match_stats["home"].get("surface")
                                    if sh and sh.get("win_rate") is not None:
                                        st.write(f"Покрытие: **{sh['win_rate']:.0%}** ({sh['matches']} матчей)")
                                    else:
                                        st.caption("Покрытие: нет данных")
                                        
                                    # Отдых
                                    rh = match_stats["home"].get("rest")
                                    if rh is not None:
                                        if rh > 30:
                                            st.caption("Отдых: данные устаревшие")
                                        else:
                                            st.write(f"Отдых: **{rh} дн.**")
                                    else:
                                        st.caption("Отдых: нет данных")
                                        
                                # === ГОСТЕВОЙ ИГРОК ===
                                with col_a:
                                    st.markdown(f"**{e['away']}**")
                                    
                                    # Форма
                                    fa = match_stats["away"].get("form")
                                    if fa and fa.get("win_rate") is not None and not fa.get("insufficient_data"):
                                        st.write(f"Форма (10): **{fa['wins']}-{fa['losses']}** ({fa['win_rate']:.0%})")
                                    else:
                                        st.caption("Форма: нет данных")
                                        
                                    # Покрытие
                                    sa = match_stats["away"].get("surface")
                                    if sa and sa.get("win_rate") is not None:
                                        st.write(f"Покрытие: **{sa['win_rate']:.0%}** ({sa['matches']} матчей)")
                                    else:
                                        st.caption("Покрытие: нет данных")
                                        
                                    # Отдых
                                    ra = match_stats["away"].get("rest")
                                    if ra is not None:
                                        if ra > 30:
                                            st.caption("Отдых: данные устаревшие")
                                        else:
                                            st.write(f"Отдых: **{ra} дн.**")
                                    else:
                                        st.caption("Отдых: нет данных")
                                        
                                # === H2H ===
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
