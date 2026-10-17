from apify_client import ApifyClient
from apify_client.errors import ApifyApiError
import pandas as pd
from datetime import datetime, timedelta
import os
import sys

# Токен берется из переменных окружения (для GitHub Actions), 
# либо из текста (если запускаешь локально)
APIFY_TOKEN = os.getenv("APIFY_TOKEN")
ACTOR_ID = "omkar-cloud/flashscore-tennis-scraper"
FILE_PATH = "flashscore_history.csv"

def fetch_data():
    if not APIFY_TOKEN or "ТВОЙ_ТОКЕН" in APIFY_TOKEN:
        print("ОШИБКА: Токен Apify не задан!")
        sys.exit(1) # Завершаем с ошибкой, чтобы GitHub Actions показал красный крестик

    client = ApifyClient(APIFY_TOKEN)
    
    # Последние 3 дня (чтобы наверстать пропущенное, если робот упал)
    # Временно ставим 30 дней для глубокой загрузки (бэкфилл)
    days_list = []
    for i in range(30):
        date_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        days_list.append(date_str)
    
    print(f"Скачиваем данные за даты: {days_list}")

    run_input = {
        "days": days_list,
        "maxResults": 5000
    }

    print("Запускаем актора в Apify...")
    try:
        run = client.actor(ACTOR_ID).call(run_input=run_input)
    except ApifyApiError as e:
        print(f"Ошибка Apify API: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Неизвестная ошибка при запуске: {e}")
        sys.exit(1)
    
    dataset_id = getattr(run, "default_dataset_id", None)
    if not dataset_id:
        dataset_id = run.get("defaultDatasetId") if isinstance(run, dict) else None
    
    if not dataset_id:
        print("Не удалось получить ID датасета. Завершаем.")
        sys.exit(1)

    print("Скачиваем результаты...")
    dataset_items = list(client.dataset(dataset_id).iterate_items())

    if not dataset_items:
        print("Данные не найдены (возможно, сегодня нет матчей).")
        return

    df_new = pd.DataFrame(dataset_items)
    
    # Проверяем, что нужные колонки вообще существуют
    if "status" in df_new.columns:
        df_new = df_new[df_new["status"] == "finished"]
    else:
        print("ВНИМАНИЕ: Колонка 'status' отсутствует в новых данных.")
        
    if df_new.empty:
        print("Нет новых завершенных матчей.")
        return

    # ===== ЛОГИКА НАКОПЛЕНИЯ =====
    if os.path.exists(FILE_PATH):
        print("Найден старый файл. Объединяем данные...")
        try:
            df_old = pd.read_csv(FILE_PATH)
            df_all = pd.concat([df_old, df_new], ignore_index=True)
        except Exception as e:
            print(f"Ошибка при чтении старого файла: {e}. Создаем новый.")
            df_all = df_new
    else:
        df_all = df_new

    # Удаляем дубликаты по ссылке на матч
    if "link" in df_all.columns:
        df_all = df_all.drop_duplicates(subset=["link"], keep="last")
    else:
        print("ВНИМАНИЕ: Колонка 'link' отсутствует. Дубликаты могут остаться.")
    
    df_all.to_csv(FILE_PATH, index=False)
    print(f"Файл обновлен! Всего уникальных матчей в базе: {len(df_all)}")

if __name__ == "__main__":
    fetch_data()
