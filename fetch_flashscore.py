from apify_client import ApifyClient
import pandas as pd

# ВСТАВЬ СВОЙ ТОКЕН ИЗ APIFY
APIFY_TOKEN = "apify_api_apify_api_nD8mKruyRQqMx255v0VZBZp2eB6g931GHY2z"
ACTOR_ID = "omkar-cloud/flashscore-tennis-scraper" # ID актора

def fetch_data():
    client = ApifyClient(APIFY_TOKEN)
    
    # Настройки запуска (забираем последние 7 дней)
    # Внимание: точные ключи фильтров зависят от актора, 
    # но обычно это daysBack и maxItems
    run_input = {
        "daysBack": 7,
        "maxItems": 3000 
    }

    print("Запускаем актора в Apify...")
    run = client.actor(ACTOR_ID).call(run_input=run_input)

    print("Скачиваем результаты...")
    dataset_items = list(client.dataset(run["defaultDatasetId"]).iterate_items())

    if not dataset_items:
        print("Данные не найдены.")
        return

    df = pd.DataFrame(dataset_items)
    
    # Очищаем данные (берем только завершенные матчи)
    df = df[df["Status"] == "finished"]
    
    # Сохраняем
    df.to_csv("flashscore_history.csv", index=False)
    print(f"Успешно сохранено {len(df)} завершенных матчей в flashscore_history.csv")

if __name__ == "__main__":
    fetch_data()
