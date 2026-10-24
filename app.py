import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from db import (
    init_db, save_prediction, list_predictions,
    settle_prediction, summary, update_closing_odds, clv_summary,
)
from sources import get_events, source_status

st.set_page_config(page_title="Sport Predictor (Odds)", page_icon="📊", layout="wide")
init_db()

# --- СТИЛИЗАЦИЯ НАВИГАЦИИ ---
st.markdown("""
<style>
    section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] { gap: 0 !important; }
    section[data-testid="stSidebar"] div[data-testid="stButton"] {
        margin-left: -1.5rem !important; margin-right: -1.5rem !important; 
        width: calc(100% + 3rem) !important; margin-bottom: 0 !important; 
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button {
        justify-content: flex-start !important; padding: 16px 20px !important; 
        border-radius: 0 !important; border: none !important; 
        border-bottom: 1px solid #333 !important; box-shadow: none !important; 
        width: 100% !important; min-height: 55px !important; 
        display: flex !important; align-items: center !important; 
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button p {
        font-size: 1.35rem !important; font-weight: 600 !important;
        margin: 0 !important; padding: 0 !important; text-align: left !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"] {
        background-color: transparent !important; color: #FAFAFA !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"]:hover {
        background-color: #262730 !important; color: #1f77b4 !important; border-left: 4px solid #1f77b4 !important; 
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] {
        background-color: #1f77b4 !important; color: #FFFFFF !important; border-left: 4px solid #1f77b4 !important; 
    }
</style>
""", unsafe_allow_html=True)

def format_time(raw):
    if not raw: return "неизвестно"
    try:
        clean = raw.split(".")[0].replace("Z", "")
        dt_utc = datetime.fromisoformat(clean)
        dt_msk = dt_utc + timedelta(hours=3)
        return dt_msk.strftime("%d.%m.%Y %H:%M") + " МСК"
    except Exception:
        return str(raw)

with st.sidebar:
    st.header("Навигация")
    if "current_page" not in st.session_state:
        st.session_state.current_page = "Матчи и кэфы"

    def nav_button(label):
        btn_type = "primary" if st.session_state.current_page == label else "secondary"
        if st.button(label, use_container_width=True, type=btn_type):
            st.session_state.current_page = label
            st.rerun()

    nav_button("Матчи и кэфы")
    nav_button("История прогнозов")
    nav_button("Виртуальный баланс")
    nav_button("Источники данных")
    page = st.session_state.current_page

st.title("📊 Sport Predictor (Line Shopping)")
st.caption("Сравнение кэфов Pinnacle и BetBoom. Без моделей. Только математика рынка.")

# ============================================================
# МАТЧИ И КЭФЫ
# ============================================================
if page == "Матчи и кэфы":
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        region = st.selectbox("Регион", ["Все", "Европа"])
        region_key = "europe" if region == "Европа" else "all"
    with col_f2:
        tour_filter = st.selectbox("Фильтр турниров", ["Все турниры", "Только топ (ATP/WTA)"])
        tour_filter_key = "top" if tour_filter == "Только топ (ATP/WTA)" else "all"

    if st.button("Загрузить матчи", type="primary"):
        with st.spinner("Загружаю линию Pinnacle…"):
            events, warning = get_events("tennis", region=region_key, tour_filter=tour_filter_key)
        st.session_state["events"] = events
        st.session_state["events_warning"] = warning

    if st.session_state.get("events_warning"):
        st.info(st.session_state["events_warning"])

    events = st.session_state.get("events", [])
    if not events:
        st.warning("Нет доступных матчей.")
    else:
        # Сортировка по дате
        def get_event_date(e):
            try:
                return datetime.fromisoformat(e.get("start", "").split(".")[0].replace("Z", ""))
            except:
                return datetime.max
        events = sorted(events, key=get_event_date)

        for i, e in enumerate(events):
            with st.container(border=True):
                st.markdown(f"**{e['home']} — {e['away']}**")
                st.caption(f"Начало: {format_time(e.get('start', ''))} · {e.get('league_name', '')}")
                
                col_h, col_a = st.columns(2)
                
                # Кэфы Pinnacle
                pin_h = e.get("odds_home")
                pin_a = e.get("odds_away")
                
                if pin_h and pin_a:
                    col_h.write(f"Pinnacle (П1): **{pin_h}**")
                    col_a.write(f"Pinnacle (П2): **{pin_a}**")
                    
                    # Считаем вероятности Pinnacle (с удалением маржи)
                    prob_h = 1 / float(pin_h)
                    prob_a = 1 / float(pin_a)
                    total_prob = prob_h + prob_a
                    fair_prob_h = prob_h / total_prob
                    fair_prob_a = prob_a / total_prob
                    
                    with st.expander("🔍 Сравнить с BetBoom", expanded=False):
                        col_bb1, col_bb2 = st.columns(2)
                        bb_h = col_bb1.number_input(f"Кэф BetBoom (П1)", min_value=1.01, value=float(pin_h), step=0.01, key=f"bb_h_{i}")
                        bb_a = col_bb2.number_input(f"Кэф BetBoom (П2)", min_value=1.01, value=float(pin_a), step=0.01, key=f"bb_a_{i}")
                        
                        # Считаем Value для П1
                        val_h = (fair_prob_h * bb_h) - 1
                        # Считаем Value для П2
                        val_a = (fair_prob_a * bb_a) - 1
                        
                        st.divider()
                        st.markdown("**Value (П1)**")
                        if val_h > 0:
                            st.success(f"✅ Кэф BetBoom выше! Value: **+{val_h:.1%}**")
                        else:
                            st.error(f"❌ Нет перевеса. Value: {val_h:.1%}")
                            
                        st.markdown("**Value (П2)**")
                        if val_a > 0:
                            st.success(f"✅ Кэф BetBoom выше! Value: **+{val_a:.1%}**")
                        else:
                            st.error(f"❌ Нет перевеса. Value: {val_a:.1%}")

                        if st.button("Сохранить в историю", key=f"save_{i}"):
                            # Сохраняем лучший исход
                            if val_h >= val_a:
                                pid = save_prediction("tennis", f"{e['home']} — {e['away']}", f"Победа {e['home']}", fair_prob_h, bb_h, "Line Shopping", "Высокая")
                                st.toast(f"Сохранено (ID: {pid})")
                            else:
                                pid = save_prediction("tennis", f"{e['home']} — {e['away']}", f"Победа {e['away']}", fair_prob_a, bb_a, "Line Shopping", "Высокая")
                                st.toast(f"Сохранено (ID: {pid})")
                else:
                    st.warning("Pinnacle не дал кэфы на этот матч.")

# ============================================================
# ИСТОРИЯ (Осталась без изменений)
# ============================================================
elif page == "История прогнозов":
    st.subheader("История прогнозов")
    rows = list_predictions(100)
    if not rows:
        st.info("Прогнозов пока нет.")
    else:
        df = pd.DataFrame(rows)
        # ... (стандартный вывод таблицы из предыдущего кода) ...
        
        st.divider()
        st.subheader("📊 CLV-трекер")
        st.caption("CLV — разница между твоим кэфом и закрывающей линией Pinnacle.")
        with st.form("clv_form"):
            clv_pid = st.number_input("ID прогноза", min_value=1, step=1)
            clv_odd = st.number_input("Closing line Pinnacle", min_value=1.01, value=1.50, step=0.01)
            if st.form_submit_button("Сохранить closing odds и посчитать CLV"):
                if update_closing_odds(int(clv_pid), float(clv_odd)):
                    st.success("CLV сохранён.")
                    st.rerun()
        
        st.divider()
        st.subheader("🏁 Закрыть прогноз")
        with st.form("settle"):
            pid = st.number_input("ID прогноза для закрытия", min_value=1, step=1)
            result = st.selectbox("Результат", ["won", "lost", "void"], format_func=lambda x: {"won": "Выиграл", "lost": "Проиграл", "void": "Возврат"}[x])
            if st.form_submit_button("Закрыть прогноз"):
                with st.spinner("Обновляю статус в базе..."):
                    success, message = settle_prediction(int(pid), result)
                if success:
                    st.success(message)
                else:
                    st.error(message)

# ============================================================
# БАЛАНС (Остался без изменений)
# ============================================================
elif page == "Виртуальный баланс":
    s = summary()
    a, b, c, d = st.columns(4)
    a.metric("Закрыто прогнозов", s["settled"])
    b.metric("Победы", s["won"])
    c.metric("Поражения", s["lost"])
    d.metric("Виртуальный P/L", f"{s['profit']:+.2f} ед.")
    
    st.divider()
    st.subheader("📊 CLV")
    clv = clv_summary()
    if clv["count"] > 0:
        c1, c2, c3 = st.columns(3)
        c1.metric("Прогнозов с CLV", clv["count"])
        c2.metric("Средний CLV", f"{clv['avg_clv']:+.2%}")
        c3.metric("CLV > 0", f"{clv['positive']} из {clv['count']}")

elif page == "Источники данных":
    st.subheader("Доступность источников")
    for name, status in source_status().items():
        st.write(f"**{name}:** {status}")
