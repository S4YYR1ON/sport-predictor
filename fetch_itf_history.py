from apify_client import ApifyClient
import pandas as pd

# ВСТАВЬ СЮДА СВОЙ ТОКЕН ИЗ APIFY
APIFY_TOKEN = "apify_api_ТВОЙ_ТОКЕН"

def fetch_tennis_data():
    # Инициализируем клиент
    client = ApifyClient(APIFY_TOKEN)

    # Настройки для парсера Flashscore (название актора может меняться, 
    # но обычно это 'lukaskrivka/flashscore-scraper' или подобное)
    run_input = {
        "sports": ["tennis"],
        "tournaments": ["itf", "challenger"], # Фильтруем только то, чего нет в Sackmann
        "maxItems": 5000, # Лимит бесплатного тарифа
        "includeFinished": True,
        "includeUpcoming": False
    }

    print("Запускаем парсер Flashscore (это займет пару минут)...")
    # Запускаем актор (имя актора нужно уточнить в их каталоге, 
    # например 'epctex/flashscore-scraper' или похожий)
    run = client.actor("epctex/flashscore-scraper").call(run_input=run_input)

    print("Парсинг завершен. Скачиваем данные...")
    # Скачиваем результаты
    dataset_items = list(client.dataset(run["defaultDatasetId"]).iterate_items())

    if not dataset_items:
        print("Не удалось найти матчи. Проверь настройки фильтра.")
        return

    # Сохраняем в CSV
    df = pd.DataFrame(dataset_items)
    df.to_csv("itf_challenger_history.csv", index=False)
    print(f"Успешно сохранено {len(df)} матчей в файл itf_challenger_history.csv")

if __name__ == "__main__":
    fetch_tennis_data()
